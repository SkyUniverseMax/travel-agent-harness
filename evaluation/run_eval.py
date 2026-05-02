"""一键评测入口：python run_eval.py 就跑完全部"""

import json
import os
import sys
import uuid
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import tools_condition

# 把父目录加到 sys.path，使 graph_chat 和 tools 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_chat.assistant import CtripAssistant, assistant_runnable, primary_assistant_tools
from graph_chat.base_data_model import (
    ToFlightBookingAssistant, ToBookCarRental,
    ToHotelBookingAssistant, ToBookExcursion,
)
from graph_chat.build_child_graph import (
    build_flight_graph, builder_hotel_graph,
    build_car_graph, builder_excursion_graph,
)
from graph_chat.llm_tavily import llm, tavily_tool
from graph_chat.state import State
from tools.flights_tools import fetch_user_flight_information
from tools.init_db import update_dates
from tools.tools_handler import create_tool_node_with_fallback


def _build_graph() -> StateGraph:
    """
    构建与第三个流程图完全一致的 graph。

    节点链路：
    START → fetch_user_info → route_to_workflow → primary_assistant
      → route_primary_assistant → 子助理 / 工具 / END
    子助理 → leave_skill → 回到 primary_assistant
    """
    # 检查/创建数据库目录
    _ensure_database()

    builder = StateGraph(State)

    # 用户信息获取节点（流程入口）
    def get_user_info(state: State):
        return {"user_info": fetch_user_flight_information.invoke({})}

    builder.add_node("fetch_user_info", get_user_info)
    builder.add_edge(START, "fetch_user_info")

    # 四个子助理的子工作流
    builder = build_flight_graph(builder)
    builder = builder_hotel_graph(builder)
    builder = build_car_graph(builder)
    builder = builder_excursion_graph(builder)

    # 主助理节点
    builder.add_node("primary_assistant", CtripAssistant(assistant_runnable))
    builder.add_node("primary_assistant_tools", create_tool_node_with_fallback(primary_assistant_tools))

    # 主助理条件路由
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
        "primary_assistant",
        route_primary_assistant,
        ["enter_update_flight", "enter_book_car_rental", "enter_book_hotel",
         "enter_book_excursion", "primary_assistant_tools", END],
    )
    builder.add_edge("primary_assistant_tools", "primary_assistant")

    # 用户回复时根据 dialog_state 栈路由
    def route_to_workflow(state: dict) -> str:
        dialog_state = state.get("dialog_state")
        if not dialog_state:
            return "primary_assistant"
        return dialog_state[-1]

    builder.add_conditional_edges("fetch_user_info", route_to_workflow)

    # 编译
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


def main():
    """
    评测主函数：
    1. 构建 graph
    2. 加载测试数据集
    3. 执行全部用例
    4. 生成控制台 + HTML 报告
    """
    print("=" * 56)
    print("  Agent 评测系统启动中...")
    print("=" * 56)

    # --- 重置数据库 ---
    print("重置数据库时间...")
    update_dates()

    # --- 构建 graph ---
    print("构建 Agent 工作流图...")
    graph = _build_graph()
    print("图构建完成。\n")

    # --- 基础配置 ---
    base_config = {
        "configurable": {
            "passenger_id": "3442 587242",
        }
    }

    # --- 加载测试用例 ---
    test_cases_path = Path(__file__).resolve().parent / "test_cases.json"
    with open(test_cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    test_cases = data["test_cases"]
    print(f"加载了 {len(test_cases)} 条测试用例。\n")

    # --- 执行评测 ---
    from evaluation.runner import run_all_cases
    results = run_all_cases(test_cases, graph, base_config, judge_llm=llm)

    # --- 生成报告 ---
    from evaluation.reporter import print_console_report, generate_html_report

    # 控制台报告
    print_console_report(results)

    # HTML 报告
    report_dir = Path(__file__).resolve().parent
    html_path = report_dir / "evaluation_report.html"
    generate_html_report(results, str(html_path))

    # --- 输出提示 ---
    print(f"\n在浏览器中打开查看可视化报告: {html_path}")


if __name__ == "__main__":
    main()
