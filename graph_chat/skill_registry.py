from dataclasses import dataclass, field
from typing import Callable, Optional

from langchain_core.messages import ToolMessage
from langchain_core.runnables import Runnable
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import tools_condition

from graph_chat.assistant import CtripAssistant
from graph_chat.base_data_model import CompleteOrEscalate
from graph_chat.entry_node import create_entry_node
from tools.tools_handler import create_tool_node_with_fallback


@dataclass
class SkillConfig:
    """定义一个业务 Skill 的完整配置。"""

    name: str
    dialog_state: str
    entry_name: str
    assistant_label: str
    runnable: Runnable
    safe_tools: list = field(default_factory=list)
    sensitive_tools: list = field(default_factory=list)
    trigger_model: Optional[type] = None


class SkillRegistry:
    """Skill 注册中心 — 单例模式，管理所有子助理的注册和子图构建。"""

    _skills: dict[str, SkillConfig] = {}
    _built: bool = False

    @classmethod
    def register(cls, skill: SkillConfig):
        """注册一个 Skill。"""
        cls._skills[skill.name] = skill

    @classmethod
    def get_all(cls) -> list[SkillConfig]:
        """返回所有已注册的 Skill。"""
        return list(cls._skills.values())

    @classmethod
    def get_by_name(cls, name: str) -> Optional[SkillConfig]:
        """按名称获取 Skill。"""
        return cls._skills.get(name)

    @classmethod
    def get_trigger_map(cls) -> dict[str, str]:
        """返回 {TriggerModelName: entry_name} 映射，供主路由使用。"""
        mapping = {}
        for skill in cls._skills.values():
            if skill.trigger_model:
                mapping[skill.trigger_model.__name__] = skill.entry_name
        return mapping

    @classmethod
    def get_interrupt_nodes(cls) -> list[str]:
        """返回所有敏感工具节点名，供 graph.compile 的 interrupt_before 使用。"""
        nodes = []
        for skill in cls._skills.values():
            if skill.sensitive_tools:
                nodes.append(f"{skill.name}_sensitive_tools")
        return nodes

    @classmethod
    def build_all_subgraphs(cls, builder: StateGraph) -> StateGraph:
        """遍历所有已注册 Skill，动态构建子图并挂载到 builder 上。"""
        if cls._built:
            return builder

        for skill in cls._skills.values():
            _build_single_skill_subgraph(builder, skill)

        cls._built = True
        return builder


def _build_single_skill_subgraph(builder: StateGraph, skill: SkillConfig):
    """为单个 Skill 构建完整的子工作流图。"""

    safe_node = f"{skill.name}_safe_tools"
    sensitive_node = f"{skill.name}_sensitive_tools"
    assistant_node = skill.name

    # 入口节点
    builder.add_node(
        skill.entry_name,
        create_entry_node(skill.assistant_label, skill.dialog_state),
    )
    builder.add_node(assistant_node, CtripAssistant(skill.runnable))
    builder.add_edge(skill.entry_name, assistant_node)

    # 安全工具节点
    if skill.safe_tools:
        builder.add_node(safe_node, create_tool_node_with_fallback(skill.safe_tools))
        builder.add_edge(safe_node, assistant_node)

    # 敏感工具节点
    if skill.sensitive_tools:
        builder.add_node(sensitive_node, create_tool_node_with_fallback(skill.sensitive_tools))
        builder.add_edge(sensitive_node, assistant_node)

    # 路由函数（闭包，捕获 skill 的上下文）
    def _route_skill(state: dict) -> str:
        route = tools_condition(state)
        if route == END:
            return END
        tool_calls = state["messages"][-1].tool_calls
        did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
        if did_cancel:
            return "leave_skill"

        safe_names = {t.name for t in skill.safe_tools}
        # 检查是否所有 tool call 都是安全的
        if tool_calls and all(tc["name"] in safe_names for tc in tool_calls):
            return safe_node
        return sensitive_node

    # 条件路由边
    destinations = []
    if skill.safe_tools:
        destinations.append(safe_node)
    if skill.sensitive_tools:
        destinations.append(sensitive_node)
    destinations.extend(["leave_skill", END])

    builder.add_conditional_edges(assistant_node, _route_skill, destinations)

    # 退出节点（只有一个 leave_skill，所有 Skill 共用）
    _ensure_leave_skill(builder)


def _ensure_leave_skill(builder: StateGraph):
    """确保 leave_skill 节点存在（只创建一次）。"""
    if "leave_skill" in builder.nodes:
        return

    def _pop_dialog_state(state: dict) -> dict:
        messages = []
        if state["messages"][-1].tool_calls:
            messages.append(
                ToolMessage(
                    content="正在恢复与主助理的对话。请回顾之前的对话并根据需要协助用户。",
                    tool_call_id=state["messages"][-1].tool_calls[0]["id"],
                )
            )
        return {"dialog_state": "pop", "messages": messages}

    builder.add_node("leave_skill", _pop_dialog_state)
    builder.add_edge("leave_skill", "primary_assistant")
