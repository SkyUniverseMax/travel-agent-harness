"""评测执行器：跑 graph、抓路由/工具调用、计算得分"""

import json
import time
from pathlib import Path

from langchain_core.messages import ToolMessage


def _extract_actual_route(events: list) -> str:
    """
    从 graph 执行过程中抓取 dialog_state 变化，作为实际路由路径。

    参数：
        events: graph.stream() 产生的 event 列表

    返回：
        str: 路由到的子助理名称（如 "update_flight"），如果没有则返回 "primary_assistant"
    """
    last_state = "primary_assistant"
    for event in events:
        ds = event.get("dialog_state")
        if ds and len(ds) > 0:
            last_state = ds[-1]
    return last_state


def _extract_tools_called(events: list) -> list:
    """
    从 graph 执行过程中抓取所有被调用的工具名称。

    参数：
        events: graph.stream() 产生的 event 列表

    返回：
        list[str]: 被调用的工具名列表（去重、保持顺序）
    """
    tools = []
    seen = set()
    for event in events:
        messages = event.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                # AIMessage 中有 tool_calls 表示 LLM 打算调用工具
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        name = tc.get("name", "")
                        if name and name not in seen:
                            tools.append(name)
                            seen.add(name)
    return tools


def _extract_response_text(events: list) -> str:
    """
    从 graph 执行结果中提取 agent 的最终文字回复。

    参数：
        events: graph.stream() 产生的 event 列表

    返回：
        str: agent 生成的文字回复内容
    """
    # 从最后一个 AIMessage 中提取 content
    for event in reversed(events):
        messages = event.get("messages")
        if isinstance(messages, list):
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_calls"):
                    text = msg.content
                    if isinstance(text, str) and len(text.strip()) > 10:
                        return text.strip()
                if hasattr(msg, "content") and msg.content and not (
                    hasattr(msg, "tool_calls") and msg.tool_calls
                ):
                    text = msg.content
                    if isinstance(text, str) and len(text.strip()) > 10:
                        return text.strip()
    return ""


def run_single_case(case: dict, graph, config: dict, judge_llm=None) -> dict:
    """
    执行单个评测用例，返回评测结果。

    参数：
        case: 测试用例字典（含 question, expected_route, expected_tools 等）
        graph: 已编译的 LangGraph 对象
        config: graph 的运行时配置（含 passenger_id, thread_id）
        judge_llm: LLM 实例，用于 LLM 评委打分

    返回：
        dict: { id, category, question, passed, score, route_match, tools_match,
                quality_score, actual_route, actual_tools, response_text, error, duration_ms }
    """
    start_time = time.time()
    result = {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "passed": False,
        "score": 0.0,
        "route_match": False,
        "tools_match": False,
        "quality_score": 0,
        "actual_route": "",
        "actual_tools": [],
        "response_text": "",
        "error": None,
        "duration_ms": 0,
        "expected_route": case["expected_route"],
        "expected_tools": case["expected_tools"],
        "description": case.get("description", ""),
    }

    try:
        all_events = []
        question = case["question"]

        # --- 第一轮：发送用户问题 ---
        events_iter = graph.stream({"messages": ("user", question)}, config, stream_mode="values")
        for event in events_iter:
            all_events.append(event)

        # --- 检查是否需要人工审批（sensitive_tools 中断）---
        current_state = graph.get_state(config)
        if current_state.next and case.get("requires_approval", False):
            # 自动审批通过，模拟用户输入 "y"
            approve_events = graph.stream(None, config, stream_mode="values")
            for event in approve_events:
                all_events.append(event)

            # 如果还有第二轮中断（如 update 类操作），继续自动审批
            current_state = graph.get_state(config)
            if current_state.next:
                approve_events2 = graph.stream(None, config, stream_mode="values")
                for event in approve_events2:
                    all_events.append(event)

        # --- 提取结果 ---
        result["actual_route"] = _extract_actual_route(all_events)
        result["actual_tools"] = _extract_tools_called(all_events)
        result["response_text"] = _extract_response_text(all_events)

        # --- 路由匹配 ---
        expected_route = case["expected_route"]
        result["route_match"] = (result["actual_route"] == expected_route)

        # --- 工具匹配 ---
        expected_tools = case.get("expected_tools", [])
        if expected_tools:
            missing = [t for t in expected_tools if t not in result["actual_tools"]]
            result["tools_match"] = len(missing) == 0
        else:
            result["tools_match"] = True  # 无预期工具时不扣分

        # --- LLM 评委打分 ---
        if judge_llm and result["response_text"]:
            from evaluation.judge import evaluate_response
            result["quality_score"] = evaluate_response(
                judge_llm,
                question,
                result["response_text"],
                case.get("description", "无预期描述"),
            )
        else:
            result["quality_score"] = 3  # 无回复时默认 3

        # --- 总分计算：路由 40% + 工具 35% + 质量 25% ---
        route_points = 1.0 if result["route_match"] else 0.0
        tools_points = 1.0 if result["tools_match"] else 0.0
        quality_normalized = result["quality_score"] / 5.0  # 1-5 归一化到 0-1

        result["score"] = route_points * 0.4 + tools_points * 0.35 + quality_normalized * 0.25
        result["passed"] = result["score"] >= 0.6  # 60 分及格

    except Exception as exc:
        result["error"] = str(exc)

    result["duration_ms"] = int((time.time() - start_time) * 1000)
    return result


def run_all_cases(test_cases: list, graph, config: dict, judge_llm=None) -> list:
    """
    批量执行所有评测用例。

    参数：
        test_cases: 测试用例列表
        graph: 已编译的 LangGraph 对象
        config: 基础运行时配置
        judge_llm: LLM 实例

    返回：
        list[dict]: 每个用例的执行结果
    """
    import uuid

    results = []
    total = len(test_cases)

    for i, case in enumerate(test_cases):
        print(f"\r执行评测用例 {i + 1}/{total}: [{case['category']}] {case['question'][:40]}...", end="", flush=True)

        case_config = {
            "configurable": {
                **config.get("configurable", {}),
                "thread_id": str(uuid.uuid4()),  # 每个用例独立的 thread_id
            }
        }
        result = run_single_case(case, graph, case_config, judge_llm=judge_llm)
        results.append(result)

    print("\n评测执行完毕。")
    return results
