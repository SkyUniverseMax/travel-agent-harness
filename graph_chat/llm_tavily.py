# 使用AI大模型
# llm = ChatOpenAI(
#     temperature=0,
#     model='deepseek-chat',
#     api_key="sk-23308eef770c47e9aeb1149038ffb243",
#     base_url="https://api.deepseek.com")
import os

from langchain_community.tools import TavilySearchResults
from langchain_openai import ChatOpenAI

# llm = ChatOpenAI(
#     temperature=0,
#     model="GLM-4-0520",
#     openai_api_key="4afc2ced3f174bc89dd17b3e47d2586d.qqcyAW2zEEqj5rY3",
#     openai_api_base="https://open.bigmodel.cn/api/paas/v4/",
# )


# llm = ChatOpenAI(   # 用的自己的服务器部署的大模型
#     temperature=0.8,
#     model="Qwen-7B",
#     openai_api_key="EMPTY",
#     openai_api_base="http://localhost:6006/v1"
# )

# llm = ChatOpenAI(  # openai的
#     temperature=0,
#     model='gpt-4o',
#     api_key="sk-doD81WgxSoF9A6xYzhgW7GUh5frRwPETI8mDq3ce4UaWnCPF",
#     base_url="https://xiaoai.plus/v1")

llm = ChatOpenAI(  # openai的
    temperature=0,
    model='qwen3.6-plus',
    api_key="sk-be6288eeec674a5a9515cf49a80327fe",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")


# 初始化搜索工具，限制结果数量为2
os.environ["TAVILY_API_KEY"] = "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"
tavily_tool = TavilySearchResults(max_results=1)