"""测试用量追踪器 (mock DB)"""
import pytest
from unittest.mock import patch, MagicMock


class TestUsageTracker:
    @pytest.fixture
    def tracker(self):
        from backend.services.usage_tracker import UsageTracker
        return UsageTracker()

    @pytest.fixture
    def mock_db(self):
        with patch("backend.services.usage_tracker.get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            yield mock_cursor

    def test_check_quota_under_limit(self, tracker, mock_db):
        mock_db.fetchone.return_value = {"cnt": 0}
        assert tracker.check_quota("user1", "text") is True

    def test_check_quota_over_limit(self, tracker, mock_db):
        mock_db.fetchone.return_value = {"cnt": 2000}
        assert tracker.check_quota("user1", "text") is False

    def test_check_quota_unknown_type(self, tracker):
        assert tracker.check_quota("user1", "unknown_type") is False

    def test_get_remaining(self, tracker, mock_db):
        mock_db.fetchone.return_value = {"cnt": 100}
        remaining = tracker.get_remaining("user1")
        assert "text" in remaining
        assert "multimodal" in remaining
        assert "image_gen" in remaining
        assert "limits" in remaining
        assert remaining["text"] == tracker.DAILY_LIMITS["text"] - 100

    def test_log_usage(self, tracker, mock_db):
        # 不应抛出异常
        tracker.log_usage("user1", "text", "test-model", tokens=100)

    def test_log_usage_unknown_type(self, tracker):
        # 不应抛出异常
        tracker.log_usage("user1", "unknown", "model")
