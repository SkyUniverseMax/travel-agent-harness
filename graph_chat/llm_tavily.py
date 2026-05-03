import os

from langchain_community.tools import TavilySearchResults
from langchain_openai import ChatOpenAI

from config import config

os.environ["TAVILY_API_KEY"] = config.TAVILY_API_KEY

llm = ChatOpenAI(
    temperature=config.LLM_TEMPERATURE,
    model=config.LLM_MODEL,
    api_key=config.LLM_API_KEY,
    base_url=config.LLM_BASE_URL,
)

tavily_tool = TavilySearchResults(max_results=1)
