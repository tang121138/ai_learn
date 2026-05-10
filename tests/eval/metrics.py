"""评测指标评分器"""
from dataclasses import dataclass, field
from tests.eval.config import METRIC_WEIGHTS, LATENCY_THRESHOLD_MS


@dataclass
class EvalResult:
    case_id: str
    category: str
    passed: bool = False
    # 各维度得分 (0-1)
    tool_accuracy: float = 0.0
    response_relevance: float = 0.0
    no_hallucination: float = 1.0
    latency_score: float = 1.0
    format_valid: float = 1.0
    # 明细
    latency_ms: float = 0.0
    response: str = ""
    tool_calls: list = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    judge_notes: str = ""

    @property
    def weighted_score(self) -> float:
        return (
            self.tool_accuracy * METRIC_WEIGHTS["tool_accuracy"]
            + self.response_relevance * METRIC_WEIGHTS["response_relevance"]
            + self.no_hallucination * METRIC_WEIGHTS["no_hallucination"]
            + self.latency_score * METRIC_WEIGHTS["latency"]
            + self.format_valid * METRIC_WEIGHTS["format_valid"]
        )


def score_tool_accuracy(expected_tool: str | None, expected_args: dict,
                        actual_tool_calls: list[dict]) -> float:
    """评估工具调用准确率"""
    if expected_tool is None:
        if not actual_tool_calls:
            return 1.0
        return 0.5  # 不需要工具但调了

    tool_names = [tc.get("function", {}).get("name", "") for tc in actual_tool_calls]
    if expected_tool not in tool_names:
        return 0.0

    # 检查参数
    for tc in actual_tool_calls:
        fn = tc.get("function", {})
        if fn.get("name") == expected_tool:
            try:
                import json
                actual_args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {})
            except json.JSONDecodeError:
                actual_args = {}
            if expected_args:
                # 参数子集匹配
                matched = sum(
                    1 for k, v in expected_args.items()
                    if k in actual_args and str(v).lower() in str(actual_args[k]).lower()
                )
                return matched / len(expected_args)
            return 1.0
    return 0.0


def score_relevance(response: str, expected_keywords: list[str]) -> float:
    """关键词命中率"""
    if not expected_keywords:
        return 1.0 if response.strip() else 0.0
    response_lower = response.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in response_lower)
    return hits / len(expected_keywords)


def score_hallucination(response: str, forbidden_keywords: list[str]) -> float:
    """幻觉检测: 禁用词出现则扣分"""
    if not forbidden_keywords:
        return 1.0
    response_lower = response.lower()
    violations = sum(1 for kw in forbidden_keywords if kw.lower() in response_lower)
    return max(0.0, 1.0 - violations * 0.5)


def score_latency(latency_ms: float, threshold_ms: int = LATENCY_THRESHOLD_MS) -> float:
    """延迟评分: 超过阈值线性扣分"""
    if latency_ms <= threshold_ms:
        return 1.0
    return max(0.0, 1.0 - (latency_ms - threshold_ms) / threshold_ms)


def score_format(response: str) -> float:
    """格式检查: 响应非空即可"""
    return 1.0 if response.strip() else 0.0
