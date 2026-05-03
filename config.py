import json
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（项目根目录）
_project_root = Path(__file__).resolve().parent.parent
_dotenv_path = _project_root / ".env"
load_dotenv(_dotenv_path, override=True)


class Config:
    """统一配置管理，所有敏感信息和可配置项集中在这里。"""

    # ===== LLM =====
    LLM_MODEL = "deepseek-v4-pro"
    LLM_API_KEY = "sk-13xxxxxxxx"
    LLM_BASE_URL = "https://api.deepseek.com"
    LLM_TEMPERATURE = 0.5

    # ===== Embedding =====
    EMBEDDING_MODEL = "multimodal-embedding-v1"
    EMBEDDING_API_KEY = "sk-xxxxxxxx"
    EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ===== Tavily =====
    TAVILY_API_KEY ="tvly-xxxxxxxx"

    # ===== 数据库（绝对路径）=====
    FLIGHT_DB = str(_project_root / os.getenv("FLIGHT_DB", "trip_assistant/travel2.sqlite"))
    TRAVEL_DB = str(_project_root / os.getenv("TRAVEL_DB", "trip_assistant/travel_new.sqlite"))
    FAQ_FILE = str(_project_root / os.getenv("FAQ_FILE", "trip_assistant/order_faq.md"))

    # ===== 日志 =====
    LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
    LOG_DIR = str(_project_root / os.getenv("LOG_DIR", "trip_assistant/logs"))

    # ===== Chroma =====
    CHROMA_PERSIST_DIR = str(_project_root / os.getenv("CHROMA_PERSIST_DIR", "trip_assistant/chroma_db"))

    # ===== MCP =====
    _mcp_raw = os.getenv("MCP_SERVERS", "[]")
    try:
        MCP_SERVERS = json.loads(_mcp_raw)
    except json.JSONDecodeError:
        MCP_SERVERS = []

    # ===== Skill 配置 =====
    SKILLS_CONFIG_PATH = str(_project_root / os.getenv("SKILLS_CONFIG_PATH", "trip_assistant/skills.json"))

    # ===== 项目根目录 =====
    PROJECT_ROOT = str(_project_root)


# 全局单例
_config_instance = None


def get_config() -> Config:
    """获取 Config 单例。"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


# 便捷导入
config = get_config()
