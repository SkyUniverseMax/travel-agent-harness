"""LLM 评委：用 LLM 评判 agent 回复质量，输出 1-5 分"""

from langchain_core.prompts import ChatPromptTemplate

JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一个 Agent 评测评委。你的任务是根据以下维度给 Agent 的回复打分（1-5 分整数）。\n\n"
        "评分维度：\n"
        "1. 相关性：回复是否切中用户的问题\n"
        "2. 完整性：是否提供了足够的信息来解决用户需求\n"
        "3. 准确性：信息是否正确（如果可用，对照用户的航班/预订记录）\n"
        "4. 清晰度：回复是否简洁易懂\n\n"
        "评分标准：\n"
        "- 5: 完全满足，所有维度优秀\n"
        "- 4: 基本满足，某个维度略有不足\n"
        "- 3: 部分满足，有遗漏或小错误\n"
        "- 2: 有重大遗漏或错误\n"
        "- 1: 完全没回答用户问题或严重错误\n\n"
        "只输出一个数字（1-5），不要输出其他任何内容。"
    ),
    (
        "user",
        "用户问题：{question}\n\n"
        "预期行为：{expected_behavior}\n\n"
        "Agent 回复内容：\n{response_text}\n\n"
        "请评分（1-5）："
    ),
])


def evaluate_response(llm, question: str, response_text: str, expected_behavior: str) -> int:
    """
    用 LLM 作为评委，对 agent 的回复打分 1-5。

    参数：
        llm: LLM 实例（复用项目已有的）
        question: 用户原始问题
        response_text: agent 的最终文字回复
        expected_behavior: 预期行为描述（如"应路由到航班助理并搜索航班"）

    返回：
        int: 1-5 分的评分，失败时返回默认分 3
    """
    if not response_text or len(response_text.strip()) < 5:
        return 1  # 空回复或过短回复直接打 1 分

    try:
        chain = JUDGE_PROMPT | llm
        result = chain.invoke({
            "question": question,
            "expected_behavior": expected_behavior,
            "response_text": response_text[:3000],  # 截断过长回复
        })
        score_text = result.content.strip()
        # 提取数字
        for char in score_text:
            if char.isdigit():
                score = int(char)
                return max(1, min(5, score))  # 限制在 1-5
        return 3  # 无法解析时给默认分
    except Exception:
        return 3  # 异常时给默认分
