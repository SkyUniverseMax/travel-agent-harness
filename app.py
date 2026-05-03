import uuid
import sys

from langchain_core.messages import ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import tools_condition

from config import config
from graph_chat.assistant import CtripAssistant, assistant_runnable, primary_assistant_tools
from graph_chat.skill_registry import SkillRegistry
from graph_chat.build_child_graph import build_all_skill_subgraphs
from graph_chat.state import State
from tools.flights_tools import fetch_user_flight_information
from tools.tools_handler import create_tool_node_with_fallback, _print_event

builder = StateGraph(State)


def get_user_info(state: State):
    return {"user_info": fetch_user_flight_information.invoke({})}


builder.add_node("fetch_user_info", get_user_info)
builder.add_edge(START, "fetch_user_info")

# 通过 SkillRegistry 动态构建所有已注册 Skill 的子图
builder = build_all_skill_subgraphs(builder)

# 主助理
builder.add_node("primary_assistant", CtripAssistant(assistant_runnable))
builder.add_node(
    "primary_assistant_tools",
    create_tool_node_with_fallback(primary_assistant_tools),
)


def route_primary_assistant(state: dict):
    route = tools_condition(state)
    if route == END:
        return END
    tool_calls = state["messages"][-1].tool_calls
    if tool_calls:
        trigger_map = SkillRegistry.get_trigger_map()
        target = trigger_map.get(tool_calls[0]["name"])
        if target:
            return target
        return "primary_assistant_tools"
    raise ValueError("无效的路由")


# 从 SkillRegistry 动态生成路由目标列表
trigger_destinations = list(SkillRegistry.get_trigger_map().values())

builder.add_conditional_edges(
    "primary_assistant",
    route_primary_assistant,
    trigger_destinations + ["primary_assistant_tools", END],
)

builder.add_edge("primary_assistant_tools", "primary_assistant")


def route_to_workflow(state: dict) -> str:
    dialog_state = state.get("dialog_state")
    if not dialog_state:
        return "primary_assistant"
    return dialog_state[-1]


builder.add_conditional_edges("fetch_user_info", route_to_workflow)

# 持久化 checkpoint（SqliteSaver）
db_path = config.CHROMA_PERSIST_DIR + "/checkpoint.db"
import os as _os
_os.makedirs(_os.path.dirname(db_path), exist_ok=True)

# SqliteSaver 需要 .db 文件路径
checkpoint_db = config.CHROMA_PERSIST_DIR + "/checkpoint.db"
memory = SqliteSaver.from_conn_string(checkpoint_db)

graph = builder.compile(
    checkpointer=memory,
    interrupt_before=SkillRegistry.get_interrupt_nodes(),
)

from tools.init_db import update_dates

session_id = str(uuid.uuid4())
update_dates()

config_runtime = {
    "configurable": {
        "passenger_id": "3442 587242",
        "thread_id": session_id,
    }
}

_printed = set()

while True:
    try:
        question = input("用户：")
    except (EOFError, KeyboardInterrupt):
        print("\n对话结束，拜拜！")
        break

    if question.lower() in ["q", "exit", "quit"]:
        print("对话结束，拜拜！")
        break

    # 使用 stream_mode="messages" 实现逐 token 流式输出
    events = graph.stream(
        {"messages": ("user", question)}, config_runtime, stream_mode="values"
    )
    for event in events:
        _print_event(event, _printed)

    current_state = graph.get_state(config_runtime)
    if current_state.next:
        user_input = input("您是否批准上述操作？输入'y'继续；否则，请说明您请求的更改。\n")
        if user_input.strip().lower() == "y":
            events = graph.stream(None, config_runtime, stream_mode="values")
            for event in events:
                _print_event(event, _printed)
        else:
            result = graph.stream(
                {
                    "messages": [
                        ToolMessage(
                            tool_call_id=event["messages"][-1].tool_calls[0]["id"],
                            content=f"Tool的调用被用户拒绝。原因：'{user_input}'。",
                        )
                    ]
                },
                config_runtime,
            )
            for event in result:
                _print_event(event, _printed)
