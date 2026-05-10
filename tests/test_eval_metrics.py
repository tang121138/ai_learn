"""测试评测管线评分器"""
import pytest
from tests.eval.metrics import (
    score_tool_accuracy, score_relevance, score_hallucination,
    score_latency, score_format, EvalResult,
)


class TestToolAccuracy:
    def test_exact_match(self):
        tool_calls = [
            {"function": {"name": "get_weather", "arguments": '{"city":"Beijing"}'}}
        ]
        score = score_tool_accuracy("get_weather", {"city": "Beijing"}, tool_calls)
        assert score == 1.0

    def test_wrong_tool(self):
        tool_calls = [
            {"function": {"name": "calculate", "arguments": '{"expression":"1+1"}'}}
        ]
        score = score_tool_accuracy("get_weather", {}, tool_calls)
        assert score == 0.0

    def test_no_tool_expected(self):
        score = score_tool_accuracy(None, {}, [])
        assert score == 1.0

    def test_no_tool_expected_but_called(self):
        tool_calls = [{"function": {"name": "get_weather", "arguments": "{}"}}]
        score = score_tool_accuracy(None, {}, tool_calls)
        assert score == 0.5

    def test_partial_args_match(self):
        tool_calls = [
            {"function": {"name": "get_weather", "arguments": '{"city":"Beijing"}'}}
        ]
        score = score_tool_accuracy("get_weather", {"city": "Beijing", "format": "json"}, tool_calls)
        assert score == 0.5  # 只匹配了 city


class TestRelevance:
    def test_all_keywords_hit(self):
        score = score_relevance("今天北京天气晴朗，温度25度", ["天气", "温度"])
        assert score == 1.0

    def test_partial_keywords(self):
        score = score_relevance("今天北京天气晴朗", ["天气", "温度"])
        assert score == 0.5

    def test_no_keywords(self):
        score = score_relevance("今天北京天气晴朗", [])
        assert score == 1.0

    def test_empty_response(self):
        score = score_relevance("", ["天气"])
        assert score == 0.0


class TestHallucination:
    def test_no_forbidden(self):
        score = score_hallucination("天气很好", ["恶意", "攻击"])
        assert score == 1.0

    def test_forbidden_found(self):
        score = score_hallucination("我可以帮你攻击网站", ["攻击"])
        assert score == 0.5

    def test_multiple_forbidden(self):
        score = score_hallucination("我可以帮你攻击网站和恶意代码", ["攻击", "恶意"])
        assert score == 0.0


class TestLatency:
    def test_under_threshold(self):
        score = score_latency(5000, 15000)
        assert score == 1.0

    def test_over_threshold(self):
        score = score_latency(20000, 15000)
        assert score < 1.0
        assert score > 0.0

    def test_way_over_threshold(self):
        score = score_latency(50000, 15000)
        assert score == 0.0


class TestFormat:
    def test_non_empty(self):
        assert score_format("hello") == 1.0

    def test_empty(self):
        assert score_format("") == 0.0


class TestEvalResult:
    def test_weighted_score(self):
        r = EvalResult(case_id="t1", category="test",
                       tool_accuracy=1.0, response_relevance=0.8,
                       no_hallucination=1.0, latency_score=0.9, format_valid=1.0)
        # 0.4*1.0 + 0.3*0.8 + 0.15*1.0 + 0.1*0.9 + 0.05*1.0 = 0.4 + 0.24 + 0.15 + 0.09 + 0.05 = 0.93
        assert 0.92 < r.weighted_score < 0.94
