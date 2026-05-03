import os
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI

from config import config
from graph_chat.base_data_model import ToFlightBookingAssistant, ToBookCarRental, ToHotelBookingAssistant, \
    ToBookExcursion
from graph_chat.llm_tavily import tavily_tool, llm
from graph_chat.state import State
from mcp_client import get_mcp_tools
from tools.flights_tools import fetch_user_flight_information, search_flights
from tools.retriever_vector import lookup_policy


class CtripAssistant:
    """LangGraph 节点：用 LLM 处理状态，最多重试 3 次以避免死循环。"""

    MAX_RETRIES = 3

    def __init__(self, runnable: Runnable):
        self.runnable = runnable

    def __call__(self, state: State, config: RunnableConfig):
        for attempt in range(self.MAX_RETRIES):
            result = self.runnable.invoke(state)
            if not result.tool_calls and (
                not result.content
                or isinstance(result.content, list)
                and not result.content[0].get("text")
            ):
                if attempt < self.MAX_RETRIES - 1:
                    messages = state["messages"] + [("user", "请提供一个真实的输出作为回应。")]
                    state = {**state, "messages": messages}
                    continue
            break
        return {"messages": result}


def _inject_time_into_messages(messages: list) -> list:
    """将当前时间注入到消息列表中，保持 system prompt 静态可缓存。"""
    time_str = f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    return [("system", time_str)] + list(messages)


# 主助理提示模板（不包含动态时间）
PRIMARY_SYSTEM_PROMPT = (
    "您是携程瑞士航空公司的客户服务助理。"
    "您的主要职责是搜索航班信息和公司政策以回答客户的查询。"
    "如果客户请求更新或取消航班、预订租车、预订酒店或获取旅行推荐，请通过调用相应的工具将任务委派给合适的专门助理。您自己无法进行这些类型的更改。"
    "只有专门助理才有权限为用户执行这些操作。"
    "用户并不知道有不同的专门助理存在，因此请不要提及他们；只需通过函数调用来安静地委派任务。"
    "向客户提供详细的信息，并且在确定信息不可用之前总是复查数据库。"
    "在搜索时，请坚持不懈。如果第一次搜索没有结果，请扩大查询范围。"
    "如果搜索无果，请扩大搜索范围后再放弃。"
    "\n\n当前用户的航班信息:\n<Flights>\n{user_info}\n</Flights>"
)

primary_assistant_prompt = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(PRIMARY_SYSTEM_PROMPT),
    MessagesPlaceholder("messages"),
])

_mcp_tools = get_mcp_tools()

primary_assistant_tools = [
    tavily_tool,
    search_flights,
    lookup_policy,
] + _mcp_tools

assistant_runnable = primary_assistant_prompt | llm.bind_tools(
    primary_assistant_tools + [
        ToFlightBookingAssistant,
        ToBookCarRental,
        ToHotelBookingAssistant,
        ToBookExcursion,
    ]
)
