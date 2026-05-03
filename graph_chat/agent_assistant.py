"""
子助理配置模块 — 通过 Skill 加载器从配置文件动态加载所有技能。

所有 Skill 的提示词、工具和触发模型现在统一在 skills.json 中管理。
如需添加新技能，只需在 skills.json 中新增定义即可，无需修改代码。
"""

from graph_chat.skill_loader import load_skills_from_config
from graph_chat.log_utils import log


def register_all_skills():
    """从配置文件加载所有 Skill 并注册到 SkillRegistry。"""
    count = load_skills_from_config()
    if count == 0:
        raise RuntimeError("未能加载任何 Skill，请检查 skills.json 配置文件")
    log.info(f"成功注册 {count} 个 Skill")


# 模块加载时自动注册
register_all_skills()
