"""
携程瑞士航空旅行助手 — Streamlit 交互式聊天页面

调用第三个流程图的完整主-子 Agent 工作流：
- 主助理接收用户请求，路由到 4 个子助理
- 子助理完成航班/酒店/租车/游览任务
- 敏感操作（预订/取消）需用户确认
- 流式输出：实时显示 Agent 的思考、路由、工具调用、最终回复
- 历史记录自动保存到 SQLite

运行：
    cd trip_assistant/evaluation_ui
    streamlit run app.py
"""

import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

# 把父目录加到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import tools_condition

from graph_chat.assistant import CtripAssistant, assistant_runnable, primary_assistant_tools
from graph_chat.base_data_model import (
    ToFlightBookingAssistant, ToBookCarRental,
    ToHotelBookingAssistant, ToBookExcursion,
)
from graph_chat.build_child_graph import (
    build_flight_graph, builder_hotel_graph,
    build_car_graph, builder_excursion_graph,
)
from graph_chat.state import State
from tools.flights_tools import fetch_user_flight_information
from tools.init_db import update_dates
from tools.tools_handler import create_tool_node_with_fallback

# ==================== 数据库（历史记录） ====================

DB_PATH = Path(__file__).resolve().parent / "chat_history.db"


@st.cache_resource
def get_db_conn():
    """获取 SQLite 连接（全局单例）"""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            session_id TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_message(role, content, session_id):
    """保存一条消息到数据库"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chat_history (timestamp, role, content, session_id)
        VALUES (?, ?, ?, ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), role, content, session_id))
    conn.commit()


def load_chat_history(session_id, limit=200):
    """加载某个 session 的对话历史"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT role, content FROM chat_history
        WHERE session_id = ?
        ORDER BY id ASC
        LIMIT ?
    """, (session_id, limit))
    return cursor.fetchall()


def get_all_sessions():
    """获取所有 session 列表（按最近活跃排序）"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT session_id, MAX(timestamp) as last_time,
               (SELECT content FROM chat_history c2
                WHERE c2.session_id = c1.session_id AND c2.role = 'user'
                ORDER BY id DESC LIMIT 1) as last_question
        FROM chat_history c1
        GROUP BY session_id
        ORDER BY last_time DESC
        LIMIT 50
    """)
    return cursor.fetchall()


def clear_session(session_id):
    """清空某个 session 的对话"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
    conn.commit()


# ==================== Graph 构建 ====================

@st.cache_resource
def build_graph():
    """构建与第三个流程图完全一致的 graph（全局缓存一次）"""
    # 确保数据库在正确位置
    _ensure_database()

    builder = StateGraph(State)

    def get_user_info(state: State):
        return {"user_info": fetch_user_flight_information.invoke({})}

    builder.add_node("fetch_user_info", get_user_info)
    builder.add_edge(START, "fetch_user_info")

    builder = build_flight_graph(builder)
    builder = builder_hotel_graph(builder)
    builder = build_car_graph(builder)
    builder = builder_excursion_graph(builder)

    builder.add_node("primary_assistant", CtripAssistant(assistant_runnable))
    builder.add_node("primary_assistant_tools", create_tool_node_with_fallback(primary_assistant_tools))

    def route_primary_assistant(state: dict):
        route = tools_condition(state)
        if route == END:
            return END
        tool_calls = state["messages"][-1].tool_calls
        if tool_calls:
            name = tool_calls[0]["name"]
            if name == ToFlightBookingAssistant.__name__:
                return "enter_update_flight"
            elif name == ToBookCarRental.__name__:
                return "enter_book_car_rental"
            elif name == ToHotelBookingAssistant.__name__:
                return "enter_book_hotel"
            elif name == ToBookExcursion.__name__:
                return "enter_book_excursion"
            return "primary_assistant_tools"
        raise ValueError("无效路由")

    builder.add_conditional_edges(
        "primary_assistant", route_primary_assistant,
        ["enter_update_flight", "enter_book_car_rental", "enter_book_hotel",
         "enter_book_excursion", "primary_assistant_tools", END],
    )
    builder.add_edge("primary_assistant_tools", "primary_assistant")

    def route_to_workflow(state: dict) -> str:
        dialog_state = state.get("dialog_state")
        if not dialog_state:
            return "primary_assistant"
        return dialog_state[-1]

    builder.add_conditional_edges("fetch_user_info", route_to_workflow)

    memory = MemorySaver()
    return builder.compile(
        checkpointer=memory,
        interrupt_before=[
            "update_flight_sensitive_tools",
            "book_car_rental_sensitive_tools",
            "book_hotel_sensitive_tools",
            "book_excursion_sensitive_tools",
        ],
    )


def _ensure_database():
    """确保数据库文件存在于项目根目录"""
    project_root = Path(__file__).resolve().parent.parent
    db_file = project_root / "travel_new.sqlite"
    backup_file = project_root / "travel2.sqlite"
    if not db_file.exists():
        raise FileNotFoundError(f"数据库文件不存在: {db_file}")
    if not backup_file.exists():
        raise FileNotFoundError(f"备份数据库不存在: {backup_file}")


# ==================== 提取 Agent 输出 ====================

def _extract_agent_message(event: dict) -> tuple:
    """
    从 event 中提取新产生的消息。
    返回：(role, content, tool_calls, is_sensitive_interrupt)
    """
    messages = event.get("messages")
    if not isinstance(messages, list):
        return None, None, None, False

    # 取最后一条消息
    msg = messages[-1]
    role = getattr(msg, "type", "unknown")
    content = getattr(msg, "content", "")
    tool_calls = getattr(msg, "tool_calls", None)

    # 判断是否是需要中断的敏感工具调用
    is_sensitive = False
    if tool_calls:
        for tc in tool_calls:
            name = tc.get("name", "")
            if name in ["update_ticket_to_new_flight", "cancel_ticket",
                        "book_hotel", "update_hotel", "cancel_hotel",
                        "book_car_rental", "update_car_rental", "cancel_car_rental",
                        "book_excursion", "update_excursion", "cancel_excursion"]:
                is_sensitive = True

    return role, content, tool_calls, is_sensitive


# ==================== 主页面 ====================

def main():
    st.set_page_config(
        page_title="携程瑞士航空旅行助手",
        page_icon="✈️",
        layout="wide",
    )

    # --- 初始化 ---
    if "graph" not in st.session_state:
        with st.spinner("🔧 加载 Agent 工作流..."):
            st.session_state.graph = build_graph()
            update_dates()
        st.toast("Agent 已就绪", icon="✅")

    # session 管理
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "waiting_approval" not in st.session_state:
        st.session_state.waiting_approval = False
    if "pending_config" not in st.session_state:
        st.session_state.pending_config = None
    if "last_event" not in st.session_state:
        st.session_state.last_event = None

    session_id = st.session_state.session_id
    config = {
        "configurable": {
            "passenger_id": "3442 587242",
            "thread_id": session_id,
        }
    }

    # --- 侧边栏：历史记录 ---
    with st.sidebar:
        st.header("📜 会话历史")

        # 新建会话按钮
        if st.button("➕ 新建会话", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.waiting_approval = False
            st.session_state.pending_config = None
            st.rerun()

        sessions = get_all_sessions()
        if sessions:
            for sid, last_time, last_question in sessions:
                label = last_question[:30] + "..." if last_question and len(last_question) > 30 else (last_question or "新会话")
                is_current = (sid == session_id)
                btn_type = "primary" if is_current else "secondary"
                if st.button(f"{'▶ ' if is_current else ''}{label}", key=f"sess_{sid}", type=btn_type, use_container_width=True):
                    st.session_state.session_id = sid
                    # 从数据库加载历史
                    history = load_chat_history(sid)
                    st.session_state.messages = [{"role": r, "content": c} for r, c in history]
                    st.session_state.waiting_approval = False
                    st.session_state.pending_config = None
                    st.rerun()
        else:
            st.caption("暂无历史会话")

        st.markdown("---")
        if st.button("🗑️ 清空当前会话", use_container_width=True):
            clear_session(session_id)
            st.session_state.messages = []
            st.rerun()

    # --- 主聊天区域 ---
    st.title("✈️ 携程瑞士航空旅行助手")
    st.caption("基于 LangGraph 多 Agent 工作流 · 支持航班/酒店/租车/游览")
    st.markdown("---")

    # 显示已有消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- 等待用户确认敏感操作 ---
    if st.session_state.waiting_approval and st.session_state.pending_config:
        st.info("⚠️ Agent 正在请求执行敏感操作（预订/取消/修改），请确认是否继续？")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ 确认执行", use_container_width=True, key="approve_btn"):
                # 继续执行
                events = st.session_state.graph.stream(None, st.session_state.pending_config, stream_mode="values")
                for event in events:
                    role, content, tool_calls, is_sensitive = _extract_agent_message(event)
                    if content:
                        with st.chat_message("assistant"):
                            st.markdown(content)
                        st.session_state.messages.append({"role": "assistant", "content": content})
                        save_message("assistant", content, session_id)

                # 检查是否还有中断
                current_state = st.session_state.graph.get_state(st.session_state.pending_config)
                st.session_state.waiting_approval = bool(current_state.next)
                st.rerun()

        with c2:
            if st.button("❌ 拒绝操作", use_container_width=True, key="reject_btn"):
                # 拒绝，发送 ToolMessage
                last_event = st.session_state.last_event
                if last_event and last_event.get("messages"):
                    last_msg = last_event["messages"][-1]
                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        tc_id = last_msg.tool_calls[0]["id"]
                        result = st.session_state.graph.stream(
                            {"messages": [ToolMessage(
                                tool_call_id=tc_id,
                                content="Tool的调用被用户拒绝。",
                            )]},
                            st.session_state.pending_config,
                        )
                        for event in result:
                            role, content, _, _ = _extract_agent_message(event)
                            if content:
                                with st.chat_message("assistant"):
                                    st.markdown(content)
                                st.session_state.messages.append({"role": "assistant", "content": content})
                                save_message("assistant", content, session_id)

                st.session_state.waiting_approval = False
                st.session_state.pending_config = None
                st.rerun()

        st.markdown("---")

    # --- 用户输入 ---
    if not st.session_state.waiting_approval:
        user_input = st.chat_input("请输入您的问题...")

        if user_input:
            # 显示用户消息
            with st.chat_message("user"):
                st.markdown(user_input)
            st.session_state.messages.append({"role": "user", "content": user_input})
            save_message("user", user_input, session_id)

            # 流式调用 Agent
            with st.chat_message("assistant"):
                # 创建一个 placeholder 用于流式输出
                placeholder = st.empty()
                full_response = ""

                # 显示思考状态
                placeholder.markdown("🤔 *Agent 正在思考...*")

                all_events = []
                events_iter = st.session_state.graph.stream(
                    {"messages": ("user", user_input)},
                    config,
                    stream_mode="values",
                )

                for event in events_iter:
                    all_events.append(event)
                    role, content, tool_calls, is_sensitive = _extract_agent_message(event)

                    if content and role == "ai":
                        # 更新显示（流式效果）
                        full_response = content
                        placeholder.markdown(full_response)
                        # 短暂延迟创造"打字"效果
                        time.sleep(0.05)

                    # 如果触发了敏感工具中断
                    if is_sensitive:
                        # 保存最后的事件，用于拒绝时构造 ToolMessage
                        st.session_state.last_event = event

                # 检查是否有待处理的中断
                current_state = st.session_state.graph.get_state(config)
                if current_state.next:
                    st.session_state.waiting_approval = True
                    st.session_state.pending_config = config
                    placeholder.markdown(full_response + "\n\n⚠️ *等待您确认敏感操作...*")
                else:
                    # 正常完成
                    if full_response:
                        placeholder.markdown(full_response)
                        st.session_state.messages.append({"role": "assistant", "content": full_response})
                        save_message("assistant", full_response, session_id)
                    else:
                        placeholder.markdown("抱歉，Agent 没有生成回复。")
                        st.session_state.messages.append({"role": "assistant", "content": "抱歉，Agent 没有生成回复。"})
                        save_message("assistant", "抱歉，Agent 没有生成回复。", session_id)

                # 如果有中断，rerun 显示确认按钮
                if st.session_state.waiting_approval:
                    st.rerun()

    # --- 页脚 ---
    st.markdown("---")
    st.caption(f"当前会话 ID: `{session_id[:8]}...` · 基于 LangGraph 多 Agent 工作流")


if __name__ == "__main__":
    main()
