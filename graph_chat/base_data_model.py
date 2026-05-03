from pydantic import BaseModel, Field, ConfigDict


class CompleteOrEscalate(BaseModel):
    """标记当前任务为已完成和/或将对话控制权升级到主助理。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cancel": True,
                "reason": "用户改变了对当前任务的想法。",
            },
            "example2": {
                "cancel": True,
                "reason": "我已经完成了任务。",
            },
            "example3": {
                "cancel": False,
                "reason": "我需要搜索用户的电子邮件或日历以获取更多信息。",
            },
        }
    )

    cancel: bool = True
    reason: str


class ToFlightBookingAssistant(BaseModel):
    """
    将工作转交给专门处理航班查询，更新和取消的助理。
    """

    request: str = Field(
        description="更新航班助理在继续之前需要澄清的任何后续问题。"
    )


class ToBookCarRental(BaseModel):
    """将工作转交给专门处理租车预订的助理。"""

    model_config = ConfigDict(
        json_schema_extra={
            "示例": {
                "location": "巴塞尔",
                "start_date": "2023-07-01",
                "end_date": "2023-07-05",
                "request": "我需要一辆带自动变速器的小型车。",
            }
        }
    )

    location: str = Field(description="用户想要租车的位置。")
    start_date: str = Field(description="租车开始日期。")
    end_date: str = Field(description="租车结束日期。")
    request: str = Field(description="用户关于租车的任何额外信息或请求。")


class ToHotelBookingAssistant(BaseModel):
    """将工作转交给专门处理酒店预订的助理。"""

    model_config = ConfigDict(
        json_schema_extra={
            "示例": {
                "location": "苏黎世",
                "checkin_date": "2023-08-15",
                "checkout_date": "2023-08-20",
                "request": "我偏好靠近市中心且房间有景观的酒店。",
            }
        }
    )

    location: str = Field(description="用户想要预订酒店的位置。")
    checkin_date: str = Field(description="酒店入住日期。")
    checkout_date: str = Field(description="酒店退房日期。")
    request: str = Field(description="用户关于酒店预订的任何额外信息或请求。")


class ToBookExcursion(BaseModel):
    """将工作转交给专门处理旅行推荐及其他游览预订的助理。"""

    model_config = ConfigDict(
        json_schema_extra={
            "示例": {
                "location": "卢塞恩",
                "request": "用户对户外活动和风景名胜感兴趣。",
            }
        }
    )

    location: str = Field(description="用户想要预订推荐旅行的位置。")
    request: str = Field(description="用户关于旅行推荐的任何额外信息或请求。")
