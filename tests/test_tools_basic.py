"""测试基础工具函数"""
import pytest
from tools.calculator import calculate
from tools.datetime_tools import get_current_time, calculate_date, days_between, weekday


class TestCalculator:
    def test_simple_addition(self):
        result = calculate("2 + 3")
        assert "5" in str(result)

    def test_multiplication(self):
        result = calculate("7 * 8")
        assert "56" in str(result)

    def test_division(self):
        result = calculate("10 / 3")
        assert "3.333" in str(result)

    def test_complex_expression(self):
        result = calculate("(2 + 3) * 4")
        assert "20" in str(result)

    def test_sqrt_not_allowed(self):
        """sqrt 不在安全白名单中，应返回错误"""
        result = calculate("sqrt(2)")
        assert "错误" in result or "非法" in result

    def test_invalid_expression(self):
        result = calculate("import os")
        assert "错误" in result.lower() or "invalid" in result.lower()

    def test_empty_expression(self):
        result = calculate("")
        assert "错误" in result.lower() or not result


class TestDateTime:
    def test_get_current_time(self):
        result = get_current_time()
        assert len(result) > 0

    def test_calculate_date(self):
        result = calculate_date("2026-01-01", 10)
        assert "2026-01-11" in result

    def test_days_between(self):
        result = days_between("2026-01-01", "2026-01-31")
        assert "30" in result

    def test_weekday(self):
        result = weekday("2026-01-01")
        # 2026-01-01 is Thursday (周四)
        assert "周四" in result or "星期四" in result
