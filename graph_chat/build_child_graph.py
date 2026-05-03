"""
子工作流图构建 — 通过 SkillRegistry 动态构建所有已注册 Skill 的子图。

保留原有函数名作为便捷入口，但实际逻辑已统一到 SkillRegistry 中。
"""

from langgraph.graph import StateGraph

from graph_chat.skill_registry import SkillRegistry
import graph_chat.agent_assistant  # noqa: F401 — 触发 Skill 自动注册


def build_all_skill_subgraphs(builder: StateGraph) -> StateGraph:
    """构建所有已注册 Skill 的子图（推荐入口）。"""
    return SkillRegistry.build_all_subgraphs(builder)


# 以下函数保持向后兼容
def build_flight_graph(builder: StateGraph) -> StateGraph:
    return SkillRegistry.build_all_subgraphs(builder)


def build_car_graph(builder: StateGraph) -> StateGraph:
    return SkillRegistry.build_all_subgraphs(builder)


def builder_hotel_graph(builder: StateGraph) -> StateGraph:
    return SkillRegistry.build_all_subgraphs(builder)


def builder_excursion_graph(builder: StateGraph) -> StateGraph:
    return SkillRegistry.build_all_subgraphs(builder)
