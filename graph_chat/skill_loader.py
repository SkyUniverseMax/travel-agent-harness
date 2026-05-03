"""
Skill 配置加载器 — 从 JSON 配置文件加载 Skill 定义，动态构建 runnable 并注册到 SkillRegistry。

支持：
- 工具名 → 工具函数的自动解析
- 触发模型名 → Pydantic 模型类的自动解析
- MCP 远程工具的自动注入
- 配置文件缺失时回退到默认硬编码配置
"""

import json
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, MessagesPlaceholder

from config import config
from graph_chat.base_data_model import (
    CompleteOrEscalate, ToFlightBookingAssistant, ToBookCarRental,
    ToHotelBookingAssistant, ToBookExcursion,
)
from graph_chat.llm_tavily import llm
from graph_chat.log_utils import log
from graph_chat.skill_registry import SkillConfig, SkillRegistry
from mcp_client import get_mcp_tools

# ===== 工具注册表（工具名 → 工具函数）=====
TOOL_REGISTRY: dict[str, object] = {}


def _build_tool_registry():
    """延迟构建工具注册表，避免循环导入。"""
    if TOOL_REGISTRY:
        return

    from tools.flights_tools import search_flights, update_ticket_to_new_flight, cancel_ticket
    from tools.hotels_tools import search_hotels, book_hotel, update_hotel, cancel_hotel
    from tools.car_tools import search_car_rentals, book_car_rental, update_car_rental, cancel_car_rental
    from tools.trip_tools import search_trip_recommendations, book_excursion, update_excursion, cancel_excursion

    _register = TOOL_REGISTRY.update
    _register({
        "search_flights": search_flights,
        "update_ticket_to_new_flight": update_ticket_to_new_flight,
        "cancel_ticket": cancel_ticket,
        "search_hotels": search_hotels,
        "book_hotel": book_hotel,
        "update_hotel": update_hotel,
        "cancel_hotel": cancel_hotel,
        "search_car_rentals": search_car_rentals,
        "book_car_rental": book_car_rental,
        "update_car_rental": update_car_rental,
        "cancel_car_rental": cancel_car_rental,
        "search_trip_recommendations": search_trip_recommendations,
        "book_excursion": book_excursion,
        "update_excursion": update_excursion,
        "cancel_excursion": cancel_excursion,
    })


# ===== 触发模型注册表（模型名 → Pydantic 类）=====
TRIGGER_MODEL_REGISTRY: dict[str, type] = {
    "ToFlightBookingAssistant": ToFlightBookingAssistant,
    "ToBookCarRental": ToBookCarRental,
    "ToHotelBookingAssistant": ToHotelBookingAssistant,
    "ToBookExcursion": ToBookExcursion,
}


def _make_static_prompt(system_text: str) -> ChatPromptTemplate:
    """构建 prompt，避免 from_messages 对中文+模板变量的解析问题。"""
    system_msg = SystemMessagePromptTemplate.from_template(system_text)
    return ChatPromptTemplate.from_messages([
        system_msg,
        MessagesPlaceholder("messages"),
    ])


def _resolve_tools(tool_names: list[str]) -> list:
    """将工具名列表解析为工具函数列表。未找到的工具记录警告并跳过。"""
    tools = []
    for name in tool_names:
        func = TOOL_REGISTRY.get(name)
        if func:
            tools.append(func)
        else:
            log.warning(f"工具 '{name}' 未在注册表中找到，已跳过")
    return tools


def load_skills_from_config(config_path: str | None = None) -> int:
    """
    从 JSON 配置文件加载 Skill 定义并注册到 SkillRegistry。

    若配置文件不存在或为空，则回退到默认硬编码配置。
    返回成功注册的技能数。
    """
    if config_path is None:
        config_path = getattr(config, 'SKILLS_CONFIG_PATH', None)
        if not config_path:
            config_path = str(Path(config.PROJECT_ROOT) / "trip_assistant" / "skills.json")

    path = Path(config_path)
    if not path.exists():
        log.warning(f"Skill 配置文件不存在: {config_path}，使用默认硬编码配置")
        return _load_default_skills()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error(f"Skill 配置文件解析失败: {e}，使用默认硬编码配置")
        return _load_default_skills()

    skills_data = data.get("skills", [])
    if not skills_data:
        log.warning("Skill 配置文件中无 Skill 定义，使用默认硬编码配置")
        return _load_default_skills()

    _build_tool_registry()
    _mcp_tools = get_mcp_tools()

    count = 0
    for skill_def in skills_data:
        try:
            name = skill_def["name"]
            system_prompt = skill_def["system_prompt"]
            safe_tool_names = skill_def.get("safe_tools", [])
            sensitive_tool_names = skill_def.get("sensitive_tools", [])
            trigger_model_name = skill_def.get("trigger_model")

            safe_tools = _resolve_tools(safe_tool_names) + _mcp_tools
            sensitive_tools = _resolve_tools(sensitive_tool_names)

            all_tools = (
                _resolve_tools(safe_tool_names)
                + _resolve_tools(sensitive_tool_names)
                + [CompleteOrEscalate]
            )

            runnable = _make_static_prompt(system_prompt) | llm.bind_tools(all_tools)

            trigger_model = TRIGGER_MODEL_REGISTRY.get(trigger_model_name) if trigger_model_name else None

            SkillRegistry.register(SkillConfig(
                name=name,
                dialog_state=skill_def["dialog_state"],
                entry_name=skill_def["entry_name"],
                assistant_label=skill_def["assistant_label"],
                runnable=runnable,
                safe_tools=safe_tools,
                sensitive_tools=sensitive_tools,
                trigger_model=trigger_model,
            ))
            log.info(f"已加载 Skill: {name}")
            count += 1
        except KeyError as e:
            log.error(f"Skill 定义缺少必要字段 {e}，已跳过")
        except Exception as e:
            log.error(f"加载 Skill 失败 ({skill_def.get('name', 'unknown')}): {e}")

    return count


def _load_default_skills() -> int:
    """回退方案：使用硬编码的默认 Skill 配置。"""
    from tools.flights_tools import search_flights, update_ticket_to_new_flight, cancel_ticket
    from tools.hotels_tools import search_hotels, book_hotel, update_hotel, cancel_hotel
    from tools.car_tools import search_car_rentals, book_car_rental, update_car_rental, cancel_car_rental
    from tools.trip_tools import search_trip_recommendations, book_excursion, update_excursion, cancel_excursion

    _mcp_tools = get_mcp_tools()

    # 航班
    flight_runnable = _make_static_prompt(
        "您是专门处理航班查询，改签和预定的助理。"
        "当用户需要帮助更新他们的预订时，主助理会将工作委托给您。"
        "请与客户确认更新后的航班详情，并告知他们任何额外费用。"
        "在搜索时，请坚持不懈。如果第一次搜索没有结果，请扩大查询范围。"
        "如果您需要更多信息或客户改变主意，请将任务升级回主助理。"
        "请记住，在相关工具成功使用后，预订才算完成。"
        "\n\n当前用户的航班信息:\n<Flights>\n{user_info}\n</Flights>"
        "\n\n如果用户需要帮助，并且您的工具都不适用，则"
        '"CompleteOrEscalate"对话给主助理。不要浪费用户的时间。不要编造无效的工具或功能。',
    ) | llm.bind_tools([search_flights, update_ticket_to_new_flight, cancel_ticket, CompleteOrEscalate])

    SkillRegistry.register(SkillConfig(
        name="update_flight",
        dialog_state="update_flight",
        entry_name="enter_update_flight",
        assistant_label="Flight Updates & Booking Assistant",
        runnable=flight_runnable,
        safe_tools=[search_flights] + _mcp_tools,
        sensitive_tools=[update_ticket_to_new_flight, cancel_ticket],
        trigger_model=ToFlightBookingAssistant,
    ))

    # 酒店
    hotel_runnable = _make_static_prompt(
        "您是专门处理酒店预订的助理。"
        "当用户需要帮助预订酒店时，主助理会将工作委托给您。"
        "根据用户的偏好搜索可用酒店，并与客户确认预订详情。"
        "在搜索时，请坚持不懈。如果第一次搜索没有结果，请扩大查询范围。"
        "如果您需要更多信息或客户改变主意，请将任务升级回主助理。"
        "请记住，在相关工具成功使用后，预订才算完成。"
        "\n\n如果用户需要帮助，并且您的工具都不适用，则"
        '"CompleteOrEscalate"对话给主助理。不要浪费用户的时间。不要编造无效的工具或功能。'
        "\n\n以下是一些你应该CompleteOrEscalate的例子：\n"
        " - '这个季节的天气怎么样？'\n"
        " - '我再考虑一下，可能单独预订'\n"
        " - '我需要弄清楚我在那里的交通方式'\n"
        " - '哦，等等，我还没预订航班，我会先订航班'\n"
        " - '酒店预订已确认'",
    ) | llm.bind_tools([search_hotels, book_hotel, update_hotel, cancel_hotel, CompleteOrEscalate])

    SkillRegistry.register(SkillConfig(
        name="book_hotel",
        dialog_state="book_hotel",
        entry_name="enter_book_hotel",
        assistant_label="酒店预订助理",
        runnable=hotel_runnable,
        safe_tools=[search_hotels] + _mcp_tools,
        sensitive_tools=[book_hotel, update_hotel, cancel_hotel],
        trigger_model=ToHotelBookingAssistant,
    ))

    # 租车
    car_runnable = _make_static_prompt(
        "您是专门处理租车预订的助理。"
        "当用户需要帮助预订租车时，主助理会将工作委托给您。"
        "根据用户的偏好搜索可用租车，并与客户确认预订详情。"
        "在搜索时，请坚持不懈。如果第一次搜索没有结果，请扩大查询范围。"
        "如果您需要更多信息或客户改变主意，请将任务升级回主助理。"
        "请记住，在相关工具成功使用后，预订才算完成。"
        "\n\n如果用户需要帮助，并且您的工具都不适用，则"
        '"CompleteOrEscalate"对话给主助理。不要浪费用户的时间。不要编造无效的工具或功能。'
        "\n\n以下是一些你应该CompleteOrEscalate的例子：\n"
        " - '这个季节的天气怎么样？'\n"
        " - '有哪些航班可供选择？'\n"
        " - '我再考虑一下，可能单独预订'\n"
        " - '哦，等等，我还没预订航班，我会先订航班'\n"
        " - '租车预订已确认'",
    ) | llm.bind_tools([search_car_rentals, book_car_rental, update_car_rental, cancel_car_rental, CompleteOrEscalate])

    SkillRegistry.register(SkillConfig(
        name="book_car_rental",
        dialog_state="book_car_rental",
        entry_name="enter_book_car_rental",
        assistant_label="Car Rental Assistant",
        runnable=car_runnable,
        safe_tools=[search_car_rentals] + _mcp_tools,
        sensitive_tools=[book_car_rental, update_car_rental, cancel_car_rental],
        trigger_model=ToBookCarRental,
    ))

    # 游览
    excursion_runnable = _make_static_prompt(
        "您是专门处理旅行推荐的助理。"
        "当用户需要帮助预订推荐的旅行时，主助理会将工作委托给您。"
        "根据用户的偏好搜索可用的旅行推荐，并与客户确认预订详情。"
        "如果您需要更多信息或客户改变主意，请将任务升级回主助理。"
        "在搜索时，请坚持不懈。如果第一次搜索没有结果，请扩大查询范围。"
        "请记住，在相关工具成功使用后，预订才算完成。"
        "\n\n如果用户需要帮助，并且您的工具都不适用，则"
        '"CompleteOrEscalate"对话给主助理。不要浪费用户的时间。不要编造无效的工具或功能。'
        "\n\n以下是一些你应该CompleteOrEscalate的例子：\n"
        " - '我再考虑一下，可能单独预订'\n"
        " - '我需要弄清楚我在那里的交通方式'\n"
        " - '哦，等等，我还没预订航班，我会先订航班'\n"
        " - '游览预订已确认！'",
    ) | llm.bind_tools([search_trip_recommendations, book_excursion, update_excursion, cancel_excursion, CompleteOrEscalate])

    SkillRegistry.register(SkillConfig(
        name="book_excursion",
        dialog_state="book_excursion",
        entry_name="enter_book_excursion",
        assistant_label="旅行推荐助理",
        runnable=excursion_runnable,
        safe_tools=[search_trip_recommendations] + _mcp_tools,
        sensitive_tools=[book_excursion, update_excursion, cancel_excursion],
        trigger_model=ToBookExcursion,
    ))

    log.info(f"已加载 {len(SkillRegistry.get_all())} 个默认 Skill")
    return len(SkillRegistry.get_all())
