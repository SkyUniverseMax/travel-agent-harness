"""
MCP Server — 将所有业务工具暴露为 MCP 远程工具。

通过 stdio 协议与主 Agent 通信，让 LLM 通过 MCP 调用所有工具。

启动方式（由 MCPClientManager 自动管理）：
    python trip_assistant/mcp_server.py

依赖：
    - mcp SDK (pip install mcp)
    - 本项目的 tools/ 模块
"""

import sys
from pathlib import Path

# 确保能导入项目工具模块（但不影响 mcp SDK 的导入路径）
# trip_assistant 已在 sys.path 中（当前脚本所在目录）
_project_dir = Path(__file__).resolve().parent
if str(_project_dir) not in sys.path:
    sys.path.insert(0, str(_project_dir))

from mcp.server.fastmcp import FastMCP

# ===== 工具函数导入 =====
from tools.flights_tools import (
    search_flights, update_ticket_to_new_flight, cancel_ticket,
    fetch_user_flight_information,
)
from tools.hotels_tools import search_hotels, book_hotel, update_hotel, cancel_hotel
from tools.car_tools import search_car_rentals, book_car_rental, update_car_rental, cancel_car_rental
from tools.trip_tools import search_trip_recommendations, book_excursion, update_excursion, cancel_excursion
from tools.retriever_vector import lookup_policy

mcp = FastMCP("Trip Tools Server")


# ===== 航班工具 =====

@mcp.tool()
def search_flights_tool(
    departure_airport: str | None = None,
    arrival_airport: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 5,
) -> str:
    """搜索航班。可按出发机场、到达机场、时间范围筛选。"""
    return str(search_flights(
        departure_airport=departure_airport,
        arrival_airport=arrival_airport,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    ))


@mcp.tool()
def update_ticket_to_new_flight_tool(ticket_no: str, new_flight_id: int) -> str:
    """将用户的机票改签到新航班。需提供机票号和新航班ID。"""
    return str(update_ticket_to_new_flight(ticket_no=ticket_no, new_flight_id=new_flight_id))


@mcp.tool()
def cancel_ticket_tool(ticket_no: str) -> str:
    """取消用户的机票。需提供机票号。"""
    return str(cancel_ticket(ticket_no=ticket_no))


@mcp.tool()
def fetch_user_flight_information_tool() -> str:
    """获取当前用户的全部机票信息，包括航班、座位等。"""
    return str(fetch_user_flight_information.invoke({}))


# ===== 酒店工具 =====

@mcp.tool()
def search_hotels_tool(
    location: str | None = None,
    name: str | None = None,
    limit: int = 5,
) -> str:
    """搜索酒店。可按位置（城市名）和酒店名筛选。"""
    return str(search_hotels(location=location, name=name, limit=limit))


@mcp.tool()
def book_hotel_tool(hotel_id: int) -> str:
    """通过酒店ID预订酒店。"""
    return str(book_hotel(hotel_id=hotel_id))


@mcp.tool()
def update_hotel_tool(hotel_id: int, checkin_date: str, checkout_date: str) -> str:
    """更新酒店预订的入住和退房日期。需提供酒店ID、入住日期、退房日期。"""
    return str(update_hotel(hotel_id=hotel_id, checkin_date=checkin_date, checkout_date=checkout_date))


@mcp.tool()
def cancel_hotel_tool(hotel_id: int) -> str:
    """取消酒店预订。需提供酒店ID。"""
    return str(cancel_hotel(hotel_id=hotel_id))


# ===== 租车工具 =====

@mcp.tool()
def search_car_rentals_tool(
    location: str | None = None,
    name: str | None = None,
    limit: int = 5,
) -> str:
    """搜索租车服务。可按位置和名称筛选。"""
    return str(search_car_rentals(location=location, name=name, limit=limit))


@mcp.tool()
def book_car_rental_tool(rental_id: int) -> str:
    """通过租车ID预订租车。"""
    return str(book_car_rental(rental_id=rental_id))


@mcp.tool()
def update_car_rental_tool(rental_id: int, start_date: str, end_date: str) -> str:
    """更新租车的开始和结束日期。需提供租车ID、开始日期、结束日期。"""
    return str(update_car_rental(rental_id=rental_id, start_date=start_date, end_date=end_date))


@mcp.tool()
def cancel_car_rental_tool(rental_id: int) -> str:
    """取消租车预订。需提供租车ID。"""
    return str(cancel_car_rental(rental_id=rental_id))


# ===== 游览/旅行推荐工具 =====

@mcp.tool()
def search_trip_recommendations_tool(
    location: str | None = None,
    name: str | None = None,
    keywords: str | None = None,
    limit: int = 5,
) -> str:
    """搜索旅行推荐/游览项目。可按位置、名称和关键词筛选。"""
    return str(search_trip_recommendations(location=location, name=name, keywords=keywords, limit=limit))


@mcp.tool()
def book_excursion_tool(recommendation_id: int) -> str:
    """通过推荐ID预订游览项目。"""
    return str(book_excursion(recommendation_id=recommendation_id))


@mcp.tool()
def update_excursion_tool(recommendation_id: int, details: str) -> str:
    """更新游览项目的详细信息。需提供推荐ID和新详情。"""
    return str(update_excursion(recommendation_id=recommendation_id, details=details))


@mcp.tool()
def cancel_excursion_tool(recommendation_id: int) -> str:
    """取消游览预订。需提供推荐ID。"""
    return str(cancel_excursion(recommendation_id=recommendation_id))


# ===== 政策查询（RAG）=====

@mcp.tool()
def lookup_policy_tool(query: str) -> str:
    """查询公司政策FAQ。输入自然语言问题，返回相关政策说明。"""
    return str(lookup_policy(query=query))


if __name__ == "__main__":
    mcp.run(transport="stdio")
