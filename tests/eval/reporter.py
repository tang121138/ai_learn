"""评测报告生成器: 终端 + Markdown + JSON 快照"""
import json
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from tests.eval.config import SNAPSHOTS_DIR, REGRESSION_THRESHOLD
from tests.eval.metrics import EvalResult


@dataclass
class EvalReport:
    dataset_name: str
    model_id: str
    total: int = 0
    passed: int = 0
    results: list[EvalResult] = field(default_factory=list)
    avg_score: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    dimension_scores: dict = field(default_factory=dict)

    def compute(self):
        self.total = len(self.results)
        if self.total == 0:
            return
        self.passed = sum(1 for r in self.results if r.weighted_score >= 0.6)
        self.avg_score = sum(r.weighted_score for r in self.results) / self.total
        latencies = sorted(r.latency_ms for r in self.results if r.latency_ms > 0)
        if latencies:
            self.avg_latency_ms = sum(latencies) / len(latencies)
            p95_idx = int(len(latencies) * 0.95)
            self.p95_latency_ms = latencies[min(p95_idx, len(latencies) - 1)]
        dims = ["tool_accuracy", "response_relevance", "no_hallucination", "latency_score", "format_valid"]
        self.dimension_scores = {
            d: sum(getattr(r, d, 0) for r in self.results) / self.total
            for d in dims
        }


def generate_terminal_report(report: EvalReport) -> str:
    """终端彩色报告"""
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

    lines = []
    sep = "=" * 46
    lines.append(f"\n{BOLD}{sep}{RESET}")
    lines.append(f"{BOLD}     Agent 评测报告 — 1号机 v1.3{RESET}")
    lines.append(f"{BOLD}{sep}{RESET}")
    lines.append(f" 数据集: {report.dataset_name}")
    lines.append(f" 模型:   {report.model_id}")
    lines.append(f" 用例数: {report.total}")
    lines.append(f" 时间:   {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"{BOLD}{sep}{RESET}")

    for dim, score in report.dimension_scores.items():
        pct = score * 100
        color = GREEN if pct >= 80 else YELLOW if pct >= 60 else RED
        label = {"tool_accuracy": "工具准确率", "response_relevance": "回复相关性",
                 "no_hallucination": "幻觉检测", "latency_score": "延迟评分",
                 "format_valid": "格式检查"}.get(dim, dim)
        lines.append(f" {label:　<10s}: {color}{pct:5.1f}%{RESET}")

    lines.append(f" 平均延迟: {report.avg_latency_ms:.0f}ms")
    lines.append(f" P95延迟:  {report.p95_latency_ms:.0f}ms")
    lines.append(f"{BOLD}{sep}{RESET}")

    final_color = GREEN if report.avg_score >= 80 else YELLOW if report.avg_score >= 60 else RED
    lines.append(f" 加权得分: {final_color}{report.avg_score * 100:.1f} / 100{RESET}")
    lines.append(f" 通过率:   {report.passed}/{report.total}")
    lines.append(f"{BOLD}{sep}{RESET}")

    # 失败用例
    failed = [r for r in report.results if r.weighted_score < 0.6]
    if failed:
        lines.append(f"\n{RED}失败用例:{RESET}")
        for r in failed:
            lines.append(f"  #{r.case_id} [{r.category}] score={r.weighted_score:.2f}")
            if r.errors:
                for e in r.errors:
                    lines.append(f"    {RED}✗{RESET} {e}")
            if r.judge_notes:
                lines.append(f"    {CYAN}Judge:{RESET} {r.judge_notes}")

    return "\n".join(lines)


def generate_markdown_report(report: EvalReport) -> str:
    """Markdown 格式报告"""
    lines = []
    lines.append(f"# Agent 评测报告")
    lines.append(f"")
    lines.append(f"| 项目 | 值 |")
    lines.append(f"|------|----|")
    lines.append(f"| 数据集 | {report.dataset_name} |")
    lines.append(f"| 模型 | {report.model_id} |")
    lines.append(f"| 用例数 | {report.total} |")
    lines.append(f"| 通过率 | {report.passed}/{report.total} |")
    lines.append(f"| 加权得分 | **{report.avg_score * 100:.1f}/100** |")
    lines.append(f"| 平均延迟 | {report.avg_latency_ms:.0f}ms |")
    lines.append(f"")
    lines.append(f"## 维度得分")
    lines.append(f"")
    lines.append(f"| 维度 | 得分 |")
    lines.append(f"|------|------|")
    for dim, score in report.dimension_scores.items():
        label = {"tool_accuracy": "工具准确率", "response_relevance": "回复相关性",
                 "no_hallucination": "幻觉检测", "latency_score": "延迟评分",
                 "format_valid": "格式检查"}.get(dim, dim)
        lines.append(f"| {label} | {score * 100:.1f}% |")
    lines.append(f"")
    lines.append(f"## 用例详情")
    lines.append(f"")
    lines.append(f"| ID | 类别 | 得分 | 延迟 | 通过 |")
    lines.append(f"|----|------|------|------|------|")
    for r in report.results:
        status = "✅" if r.weighted_score >= 0.6 else "❌"
        lines.append(f"| {r.case_id} | {r.category} | {r.weighted_score:.2f} | {r.latency_ms:.0f}ms | {status} |")
    return "\n".join(lines)


def save_snapshot(report: EvalReport) -> str:
    """保存评测快照，返回文件路径"""
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
    filename = f"{report.dataset_name}_{report.model_id.replace('/', '_')}_{ts}.json"
    path = os.path.join(SNAPSHOTS_DIR, filename)
    data = {
        "dataset": report.dataset_name,
        "model": report.model_id,
        "total": report.total,
        "passed": report.passed,
        "avg_score": report.avg_score,
        "avg_latency_ms": report.avg_latency_ms,
        "p95_latency_ms": report.p95_latency_ms,
        "dimension_scores": report.dimension_scores,
        "results": [
            {
                "id": r.case_id,
                "category": r.category,
                "score": r.weighted_score,
                "latency_ms": r.latency_ms,
                "errors": r.errors,
                "judge_notes": r.judge_notes,
            }
            for r in report.results
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def compare_with_last(report: EvalReport) -> str:
    """与上次快照对比，生成回归检测报告"""
    prefix = f"{report.dataset_name}_{report.model_id.replace('/', '_')}"
    snapshots = sorted(
        [f for f in os.listdir(SNAPSHOTS_DIR) if f.startswith(prefix) and f.endswith(".json")],
        reverse=True,
    )
    if len(snapshots) < 1:
        return ""

    last_path = os.path.join(SNAPSHOTS_DIR, snapshots[0])
    with open(last_path, "r", encoding="utf-8") as f:
        last = json.load(f)

    lines = []
    lines.append("\n--- 回归检测 ---")
    score_diff = (report.avg_score - last["avg_score"]) * 100
    if abs(score_diff) >= REGRESSION_THRESHOLD:
        direction = "↓ 退化" if score_diff < 0 else "↑ 提升"
        lines.append(f"综合得分变化: {direction} {abs(score_diff):.1f} 分")

    # 比较维度
    for dim in report.dimension_scores:
        current = report.dimension_scores[dim] * 100
        previous = last.get("dimension_scores", {}).get(dim, 0) * 100
        diff = current - previous
        if abs(diff) >= REGRESSION_THRESHOLD:
            direction = "↓" if diff < 0 else "↑"
            label = {"tool_accuracy": "工具准确率", "response_relevance": "回复相关性",
                     "no_hallucination": "幻觉检测", "latency_score": "延迟评分",
                     "format_valid": "格式检查"}.get(dim, dim)
            lines.append(f"  {label}: {direction} {abs(diff):.1f}%")

    # 新增失败用例
    last_failed = {r["id"] for r in last.get("results", []) if r["score"] < 0.6}
    current_failed = {r.case_id for r in report.results if r.weighted_score < 0.6}
    new_failed = current_failed - last_failed
    fixed = last_failed - current_failed
    if new_failed:
        lines.append(f"❌ 新增失败: {', '.join(sorted(new_failed))}")
    if fixed:
        lines.append(f"✅ 已修复: {', '.join(sorted(fixed))}")

    return "\n".join(lines) if len(lines) > 1 else "\n回归检测: 无显著变化"
