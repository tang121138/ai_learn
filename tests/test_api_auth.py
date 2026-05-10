"""测试认证 API 端点

注意: API 集成测试需要真实的 TestClient 环境。
核心逻辑由单元测试覆盖，此文件作为 API 测试骨架保留。
"""
import pytest


@pytest.mark.skip(reason="需要完整 TestClient 环境 (数据库 + JWT)，在 CI 中配置后启用")
class TestAuthEndpoints:
    def test_register_success(self):
        pass

    def test_register_duplicate(self):
        pass

    def test_login_success(self):
        pass

    def test_login_failure(self):
        pass

    def test_unauthenticated_access(self):
        pass


def test_health_endpoint_schema():
    """验证健康检查端点路由定义正确"""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.main import app
    routes = [r.path for r in app.routes if hasattr(r, 'path')]
    assert "/api/health" in routes
    assert "/api/auth/login" in routes
    assert "/api/auth/register" in routes
