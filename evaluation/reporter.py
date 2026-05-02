"""评测报告生成器：控制台 + HTML"""

import json
from datetime import datetime
from pathlib import Path


def print_console_report(results: list):
    """
    在控制台打印评测总结，显示：汇总表格、分类统计、失败用例列表。

    参数：
        results: runner.run_all_cases() 返回的结果列表
    """
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    avg_score = sum(r["score"] for r in results) / total if total > 0 else 0

    # 顶部汇总
    print("\n" + "=" * 72)
    print("  携程瑞士航空旅行助手 — Agent 评测报告")
    print("=" * 72)
    print(f"  评测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  测试用例总数: {total}    通过: {passed}    失败: {failed}")
    print(f"  通过率: {passed / total * 100:.1f}%    平均得分: {avg_score:.2%}")
    print("-" * 72)

    # 按类别统计
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0, "scores": []}
        categories[cat]["total"] += 1
        if r["passed"]:
            categories[cat]["passed"] += 1
        categories[cat]["scores"].append(r["score"])

    print(f"  {'分类':<16s} {'用例数':>6s} {'通过':>6s} {'通过率':>8s} {'平均分':>8s}")
    print("  " + "-" * 50)
    for cat_name, stats in sorted(categories.items()):
        cat_avg = sum(stats["scores"]) / len(stats["scores"])
        cat_rate = stats["passed"] / stats["total"] * 100
        print(
            f"  {cat_name:<16s} {stats['total']:>6d} {stats['passed']:>6d}"
            f" {cat_rate:>7.1f}% {cat_avg:>7.2%}"
        )

    # 各项指标
    route_accuracy = sum(1 for r in results if r["route_match"]) / total * 100
    tools_accuracy = sum(1 for r in results if r["tools_match"]) / total * 100
    avg_quality = sum(r["quality_score"] for r in results) / total
    print("-" * 72)
    print(f"  路由准确率: {route_accuracy:.1f}%    工具调用准确率: {tools_accuracy:.1f}%"
          f"    平均回复质量: {avg_quality:.1f}/5")
    print("=" * 72)

    # 失败用例详情
    failed_cases = [r for r in results if not r["passed"]]
    if failed_cases:
        print("\n  失败用例详情:")
        for f in failed_cases:
            print(f"  [{f['id']}] {f['category']}: {f['question']}")
            print(f"       预期路由: {f['expected_route']} → 实际: {f['actual_route']} {'✓' if f['route_match'] else '✗'}")
            if f["expected_tools"]:
                print(f"       预期工具: {f['expected_tools']} → 实际: {f['actual_tools']} {'✓' if f['tools_match'] else '✗'}")
            print(f"       回复质量: {f['quality_score']}/5    总分: {f['score']:.2%}")
            if f["error"]:
                print(f"       错误: {f['error']}")
            if f["response_text"]:
                print(f"       回复: {f['response_text'][:200]}...")
            print()
    print()


def generate_html_report(results: list, output_path: str = "evaluation_report.html"):
    """
    生成 HTML 可视化报告文件，包含统计图表、详细日志。

    参数：
        results: runner.run_all_cases() 返回的结果列表
        output_path: 输出 HTML 文件路径
    """
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    avg_score = sum(r["score"] for r in results) / total if total > 0 else 0

    # 分类统计
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r["passed"]:
            categories[cat]["passed"] += 1

    # 生成表格行
    rows_html = ""
    for r in results:
        status_class = "pass" if r["passed"] else "fail"
        status_text = "PASS" if r["passed"] else "FAIL"
        rows_html += f"""
        <tr class="{status_class}">
            <td>{r['id']}</td>
            <td>{r['category']}</td>
            <td>{r['question']}</td>
            <td>{r['expected_route']}</td>
            <td>{r['actual_route']}</td>
            <td>{', '.join(r['actual_tools']) if r['actual_tools'] else '—'}</td>
            <td>{r['quality_score']}/5</td>
            <td>{r['score']:.0%}</td>
            <td class="status-{status_class}">{status_text}</td>
        </tr>"""

    # 分类行
    cat_rows = ""
    for name, stats in sorted(categories.items()):
        rate = stats["passed"] / stats["total"] * 100
        cat_rows += f"""
            <tr>
                <td>{name}</td>
                <td>{stats['total']}</td>
                <td>{stats['passed']}</td>
                <td>{rate:.1f}%</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>Agent 评测报告 — 携程瑞士航空旅行助手</title>
    <style>
        body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; margin: 40px auto; max-width: 1100px;
               color: #1a1a2e; background: #f8f9fa; }}
        h1 {{ text-align: center; color: #0f3460; }}
        .summary {{ display: flex; gap: 20px; margin: 30px 0; flex-wrap: wrap; }}
        .card {{ flex: 1; min-width: 180px; background: white; padding: 20px; border-radius: 12px;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }}
        .card .num {{ font-size: 36px; font-weight: bold; color: #e94560; }}
        .card .num.green {{ color: #16c79a; }}
        .card .label {{ color: #666; margin-top: 6px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; background: white;
                 border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
        th {{ background: #0f3460; color: white; padding: 12px 10px; text-align: left; font-weight: 500; }}
        td {{ padding: 10px; border-bottom: 1px solid #eee; font-size: 14px; }}
        tr:hover {{ background: #f1f3f5; }}
        .pass {{  }}
        .fail {{ background: #fff5f5; }}
        .status-pass {{ color: #16c79a; font-weight: bold; }}
        .status-fail {{ color: #e94560; font-weight: bold; }}
        .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 40px; }}
    </style>
</head>
<body>
    <h1>Agent 评测报告</h1>
    <p style="text-align:center;color:#666;">携程瑞士航空旅行助手 — 第三个流程图 (多 Agent 工作流)</p>

    <div class="summary">
        <div class="card">
            <div class="num">{total}</div>
            <div class="label">测试用例总数</div>
        </div>
        <div class="card">
            <div class="num green">{passed}</div>
            <div class="label">通过</div>
        </div>
        <div class="card">
            <div class="num">{total - passed}</div>
            <div class="label">失败</div>
        </div>
        <div class="card">
            <div class="num green">{passed / total * 100:.1f}%</div>
            <div class="label">通过率</div>
        </div>
        <div class="card">
            <div class="num">{avg_score:.0%}</div>
            <div class="label">平均得分</div>
        </div>
    </div>

    <h2>分类统计</h2>
    <table>
        <tr><th>类别</th><th>用例数</th><th>通过</th><th>通过率</th></tr>
        {cat_rows}
    </table>

    <h2>详细结果</h2>
    <table>
        <tr>
            <th>ID</th><th>分类</th><th>问题</th><th>预期路由</th>
            <th>实际路由</th><th>调用的工具</th><th>回复质量</th><th>得分</th><th>结果</th>
        </tr>
        {rows_html}
    </table>

    <div class="footer">
        生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"HTML 报告已生成: {output_path}")


# ==================== 基线对比功能 ====================

BASELINE_FILENAME = "baseline.json"


def save_baseline(results: list, output_dir: str):
    """
    将当前评测结果保存为基线文件。

    基线文件 (baseline.json) 用于后续对比，记录每条用例和汇总指标。
    参数：
        results: 评测结果列表
        output_dir: 保存目录路径
    """
    total = len(results)
    summary = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": total,
        "passed": sum(1 for r in results if r["passed"]),
        "avg_score": sum(r["score"] for r in results) / total if total > 0 else 0,
        "route_accuracy": sum(1 for r in results if r["route_match"]) / total * 100 if total else 0,
        "tools_accuracy": sum(1 for r in results if r["tools_match"]) / total * 100 if total else 0,
        "avg_quality": sum(r["quality_score"] for r in results) / total if total else 0,
        "cases": [
            {
                "id": r["id"],
                "category": r["category"],
                "question": r["question"],
                "score": r["score"],
                "passed": r["passed"],
                "route_match": r["route_match"],
                "tools_match": r["tools_match"],
                "quality_score": r["quality_score"],
            }
            for r in results
        ],
    }
    filepath = Path(output_dir) / BASELINE_FILENAME
    filepath.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"基线已保存: {filepath}")


def load_baseline(base_dir: str) -> dict | None:
    """
    加载之前的基线文件。
    如果没有基线文件，返回 None。
    """
    filepath = Path(base_dir) / BASELINE_FILENAME
    if not filepath.exists():
        return None
    return json.loads(filepath.read_text(encoding="utf-8"))


def print_comparison(current: list, baseline: dict):
    """
    对比本次评测与基线，在控制台打印变化详情。

    输出：
    - 整体指标变化（通过率/平均分/路由准确率/工具准确率/回复质量）
    - 每个分类的变化
    - 变好/变差的用例
    """
    total = len(current)
    cur_passed = sum(1 for r in current if r["passed"])
    cur_avg = sum(r["score"] for r in current) / total if total else 0
    cur_route = sum(1 for r in current if r["route_match"]) / total * 100
    cur_tools = sum(1 for r in current if r["tools_match"]) / total * 100
    cur_quality = sum(r["quality_score"] for r in current) / total if total else 0

    bl_passed = baseline["passed"]
    bl_total = baseline["total_cases"]
    bl_avg = baseline["avg_score"]
    bl_route = baseline["route_accuracy"]
    bl_tools = baseline["tools_accuracy"]
    bl_quality = baseline["avg_quality"]

    def _arrow(new_val, old_val, higher_is_better=True):
        """计算差值，返回带箭头的字符串。"""
        diff = new_val - old_val
        if abs(diff) < 0.1:
            return "→  持平"
        up = (diff > 0) == higher_is_better
        arrow = "↑" if up else "↓"
        return f"{arrow}  {'+' if diff > 0 else ''}{diff:.1f}%"

    print("\n" + "=" * 72)
    print("  基线对比报告")
    print("=" * 72)
    print(f"  基线时间: {baseline['saved_at']}  ({bl_passed}/{bl_total} 通过)")
    print("-" * 72)
    print(f"  {'指标':<20s} {'基线值':>12s} {'本次值':>12s} {'变化':>14s}")
    print("  " + "-" * 60)

    # 通过率对比
    bl_rate = bl_passed / bl_total * 100
    cur_rate = cur_passed / total * 100
    print(f"  {'通过率':<20s} {bl_rate:>11.1f}% {cur_rate:>11.1f}% {_arrow(cur_rate, bl_rate):>14s}")

    # 平均得分对比
    print(f"  {'平均得分':<20s} {bl_avg:>11.1%} {cur_avg:>11.1%} {_arrow(cur_avg * 100, bl_avg * 100):>14s}")

    # 路由准确率对比
    print(f"  {'路由准确率':<20s} {bl_route:>11.1f}% {cur_route:>11.1f}% {_arrow(cur_route, bl_route):>14s}")

    # 工具准确率对比
    print(f"  {'工具调用准确率':<20s} {bl_tools:>11.1f}% {cur_tools:>11.1f}% {_arrow(cur_tools, bl_tools):>14s}")

    # 回复质量对比
    print(f"  {'回复质量':<20s} {bl_quality:>11.1f}/5 {cur_quality:>11.1f}/5"
          f" {_arrow(cur_quality * 20, bl_quality * 20):>14s}")

    # 按类别对比
    print("\n" + "-" * 72)
    print(f"  {'分类变化':<16s} {'基线通过率':>10s} {'本次通过率':>10s} {'变化':>10s}")
    print("  " + "-" * 52)

    # 从基线中按类别汇总
    bl_cats = {}
    for c in baseline["cases"]:
        cat = c["category"]
        if cat not in bl_cats:
            bl_cats[cat] = {"total": 0, "passed": 0}
        bl_cats[cat]["total"] += 1
        if c["passed"]:
            bl_cats[cat]["passed"] += 1

    cur_cats = {}
    for r in current:
        cat = r["category"]
        if cat not in cur_cats:
            cur_cats[cat] = {"total": 0, "passed": 0}
        cur_cats[cat]["total"] += 1
        if r["passed"]:
            cur_cats[cat]["passed"] += 1

    all_cats = sorted(set(list(bl_cats.keys()) + list(cur_cats.keys())))
    for cat in all_cats:
        bl_rate_cat = bl_cats[cat]["passed"] / bl_cats[cat]["total"] * 100 if cat in bl_cats else 0
        cur_rate_cat = cur_cats[cat]["passed"] / cur_cats[cat]["total"] * 100 if cat in cur_cats else 0
        diff_text = _arrow(cur_rate_cat, bl_rate_cat)
        print(f"  {cat:<16s} {bl_rate_cat:>9.1f}% {cur_rate_cat:>9.1f}% {diff_text:>10s}")

    # 具体变化的用例
    improved = []
    worsened = []
    bl_cases_map = {c["id"]: c for c in baseline["cases"]}
    for r in current:
        cid = r["id"]
        if cid in bl_cases_map:
            old_passed = bl_cases_map[cid]["passed"]
            if r["passed"] and not old_passed:
                improved.append(r)
            elif not r["passed"] and old_passed:
                worsened.append(r)

    if improved:
        print("\n  ✅ 变好的用例:")
        for r in improved:
            old_score = bl_cases_map[r["id"]]["score"]
            print(f"     [{r['id']}] {r['category']}: {r['question'][:40]}... "
                  f"(得分 {old_score:.0%} → {r['score']:.0%})")

    if worsened:
        print("\n  ❌ 变差的用例:")
        for r in worsened:
            old_score = bl_cases_map[r["id"]]["score"]
            print(f"     [{r['id']}] {r['category']}: {r['question'][:40]}... "
                  f"(得分 {old_score:.0%} → {r['score']:.0%})")

    if not improved and not worsened:
        print("\n  — 所有用例状态与基线一致，无变化。")

    print("\n" + "=" * 72 + "\n")
