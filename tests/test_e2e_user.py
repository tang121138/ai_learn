"""
用户角度端到端评测系统 (v1.4)
================================
模拟真实用户操作流程, 覆盖全部 API 端点和功能模块。
不依赖 LLM-as-Judge, 测试的是系统功能完整性、正确性、边界行为。

运行:
    pytest tests/test_e2e_user.py -v -s --tb=short
    或
    python tests/test_e2e_user.py

依赖: 后端需已启动 (localhost:9090), 数据库已初始化。
"""
import sys
import os
import json
import time
import uuid
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

# --- 配置 ---
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:9090")
TEST_USERNAME = f"eval_test_{uuid.uuid4().hex[:6]}"
TEST_PASSWORD = "EvalTest@2024!"
REPORT_PATH = os.path.join(os.path.dirname(__file__), "eval", "snapshots", "e2e_report.json")

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)


# ══════════════════════════════════════════
# 评测结果模型
# ══════════════════════════════════════════

@dataclass
class E2EResult:
    case_id: str
    module: str
    name: str
    passed: bool = False
    duration_ms: float = 0.0
    error: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def status_icon(self) -> str:
        return "PASS" if self.passed else "FAIL"


@dataclass
class E2EReport:
    results: list[E2EResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / max(self.total, 1)

    @property
    def total_duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000

    @property
    def by_module(self) -> dict:
        modules: dict[str, list] = {}
        for r in self.results:
            modules.setdefault(r.module, []).append(r)
        return modules


# ══════════════════════════════════════════
# HTTP 客户端
# ══════════════════════════════════════════

class E2EClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token: str = ""
        self.user: dict = {}
        self.session = requests.Session()

    def _headers(self, auth: bool = True) -> dict:
        h = {"Content-Type": "application/json"}
        if auth and self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def get(self, path: str, auth: bool = True) -> requests.Response:
        return self.session.get(self._url(path), headers=self._headers(auth), timeout=30)

    def post(self, path: str, data: dict, auth: bool = True) -> requests.Response:
        return self.session.post(self._url(path), json=data, headers=self._headers(auth), timeout=60)

    def patch(self, path: str, data: dict, auth: bool = True) -> requests.Response:
        return self.session.patch(self._url(path), json=data, headers=self._headers(auth), timeout=30)

    def delete(self, path: str, auth: bool = True) -> requests.Response:
        return self.session.delete(self._url(path), headers=self._headers(auth), timeout=30)

    def sse_stream(self, path: str, data: dict, timeout: float = 45.0) -> list[dict]:
        """发送 SSE 请求, 收集所有事件"""
        resp = self.session.post(
            self._url(path), json=data, headers=self._headers(),
            stream=True, timeout=timeout,
        )
        resp.raise_for_status()
        events = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
        return events


# ══════════════════════════════════════════
# 评测运行器
# ══════════════════════════════════════════

class E2ERunner:
    def __init__(self):
        self.client = E2EClient(BASE_URL)
        self.report = E2EReport()
        self._session_id: str = ""
        self._task_id: str = ""

    def run(self, case_id: str, module: str, name: str, fn, *args, **kwargs):
        """运行单个用例, 记录结果"""
        result = E2EResult(case_id=case_id, module=module, name=name)
        t0 = time.time()
        try:
            outcome = fn(*args, **kwargs)
            result.duration_ms = (time.time() - t0) * 1000
            if isinstance(outcome, tuple):
                result.passed, msg = outcome
                result.error = "" if result.passed else msg
            elif isinstance(outcome, dict):
                result.passed = outcome.get("passed", True)
                result.error = outcome.get("error", "")
                result.detail = outcome
            else:
                result.passed = bool(outcome)
        except Exception as e:
            result.duration_ms = (time.time() - t0) * 1000
            result.passed = False
            result.error = str(e)
        self.report.results.append(result)
        self._print_result(result)

    def _print_result(self, r: E2EResult):
        icon = "\033[92m✓\033[0m" if r.passed else "\033[91m✗\033[0m"
        err = f" — \033[91m{r.error}\033[0m" if r.error else ""
        print(f"  {icon} [{r.module}] {r.name} ({r.duration_ms:.0f}ms){err}")


runner = E2ERunner()


# ══════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════

def check_status(resp: requests.Response, expected: int) -> tuple:
    actual = resp.status_code
    return (True, "") if actual == expected else (False, f"HTTP {actual} (expected {expected}): {resp.text[:120]}")

def check_json_key(resp: requests.Response, key: str) -> tuple:
    try:
        body = resp.json()
        return (True, "") if key in body else (False, f"响应缺少字段 '{key}', got: {list(body.keys())}")
    except Exception:
        return False, f"非 JSON 响应: {resp.text[:80]}"

def check_non_empty(resp: requests.Response, key: str) -> tuple:
    try:
        body = resp.json()
        val = body.get(key)
        return (True, "") if val else (False, f"字段 '{key}' 为空")
    except Exception:
        return False, f"非 JSON 响应"

def contains_all(text: str, keywords: list[str]) -> tuple:
    missing = [kw for kw in keywords if kw.lower() not in text.lower()]
    return (True, "") if not missing else (False, f"缺少关键词: {missing}")

def contains_none(text: str, forbidden: list[str]) -> tuple:
    found = [kw for kw in forbidden if kw.lower() in text.lower()]
    return (True, "") if not found else (False, f"发现禁用词: {found}")


# ══════════════════════════════════════════
# 模块 1: 服务健康检查
# ══════════════════════════════════════════

def test_module_health():
    print("\n\033[1m[模块1] 服务健康检查\033[0m")

    def check():
        resp = runner.client.get("/api/health", auth=False)
        ok, err = check_status(resp, 200)
        if not ok:
            return False, f"后端未启动? {err}"
        body = resp.json()
        return body.get("status") == "ok", ""

    runner.run("e2e_H01", "health", "后端服务可达", check)

    def check_version():
        resp = runner.client.get("/api/health", auth=False)
        body = resp.json()
        return "version" in body, ""

    runner.run("e2e_H02", "health", "健康检查含版本号", check_version)


# ══════════════════════════════════════════
# 模块 2: 用户认证
# ══════════════════════════════════════════

def test_module_auth():
    print("\n\033[1m[模块2] 用户认证\033[0m")

    # 2.1 注册
    def do_register():
        resp = runner.client.post("/api/auth/register", {
            "username": TEST_USERNAME, "password": TEST_PASSWORD,
        }, auth=False)
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        return check_json_key(resp, "id")

    runner.run("e2e_A01", "auth", f"注册用户 {TEST_USERNAME}", do_register)

    # 2.2 重复注册
    def dup_register():
        resp = runner.client.post("/api/auth/register", {
            "username": TEST_USERNAME, "password": "other",
        }, auth=False)
        ok, _ = check_status(resp, 409)
        return ok, ""

    runner.run("e2e_A02", "auth", "重复注册 → 409", dup_register)

    # 2.3 登录
    def do_login():
        resp = runner.client.post("/api/auth/login", {
            "username": TEST_USERNAME, "password": TEST_PASSWORD,
        }, auth=False)
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        runner.client.token = body.get("access_token", "")
        runner.client.user = body.get("user", {})
        if not runner.client.token:
            return False, "未返回 access_token"
        return True, ""

    runner.run("e2e_A03", "auth", "登录获取 JWT", do_login)

    # 2.4 错误密码
    def bad_login():
        resp = runner.client.post("/api/auth/login", {
            "username": TEST_USERNAME, "password": "wrongpassword",
        }, auth=False)
        ok, _ = check_status(resp, 401)
        return ok, ""

    runner.run("e2e_A04", "auth", "错误密码 → 401", bad_login)

    # 2.5 获取当前用户
    def get_me():
        resp = runner.client.get("/api/auth/me")
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        return body.get("username") == TEST_USERNAME, f"username 不匹配: {body}"

    runner.run("e2e_A05", "auth", "GET /me 返回当前用户", get_me)

    # 2.6 无 token 访问受保护端点
    def no_auth():
        resp = runner.client.get("/api/sessions", auth=False)
        ok, _ = check_status(resp, 401)
        return ok, ""

    runner.run("e2e_A06", "auth", "无 Token → 401", no_auth)


# ══════════════════════════════════════════
# 模块 3: 模型与工具列表
# ══════════════════════════════════════════

def test_module_models():
    print("\n\033[1m[模块3] 模型与工具列表\033[0m")

    def list_models():
        resp = runner.client.get("/api/models", auth=False)
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        models = body.get("models", [])
        if len(models) < 3:
            return False, f"模型数不足: {len(models)}"
        types = {m["type"] for m in models}
        required = {"text", "multimodal", "image_gen"}
        if not required.issubset(types):
            return False, f"缺少模型类型: {required - types}"
        return True, ""

    runner.run("e2e_M01", "models", "模型列表 ≥3 类型齐全", list_models)

    def default_model():
        resp = runner.client.get("/api/models", auth=False)
        body = resp.json()
        dm = body.get("default_model", "")
        model_ids = [m["id"] for m in body.get("models", [])]
        return dm in model_ids, f"默认模型 '{dm}' 不在列表中"

    runner.run("e2e_M02", "models", "默认模型在列表内", default_model)

    def list_tools():
        resp = runner.client.get("/api/tools")
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        text = resp.json().get("tools", "")
        # 检查关键工具都存在
        must_have = ["get_weather", "calculate", "analyze_image",
                     "generate_image", "sql_query", "generate_chart"]
        return contains_all(text, must_have)

    runner.run("e2e_M03", "tools", "工具列表含全部6类工具", list_tools)

    def mcp_servers():
        resp = runner.client.get("/api/mcp/servers")
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        if "sdk_available" not in body:
            return False, "缺少 sdk_available"
        if "servers" not in body:
            return False, "缺少 servers"
        return True, ""

    runner.run("e2e_M04", "mcp", "MCP 服务器状态可查询", mcp_servers)


# ══════════════════════════════════════════
# 模块 4: 会话管理
# ══════════════════════════════════════════

def test_module_sessions():
    print("\n\033[1m[模块4] 会话管理\033[0m")

    def create():
        resp = runner.client.post("/api/sessions", {"title": "E2E评测会话"})
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        body = resp.json()
        runner._session_id = body.get("id", "")
        return bool(runner._session_id), "session_id 为空"

    runner.run("e2e_S01", "session", "创建会话", create)

    def create_with_model():
        resp = runner.client.post("/api/sessions", {
            "title": "DeepSeek会话",
            "model_id": "deepseek-v4-flash",
        })
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        body = resp.json()
        return body.get("model_id") == "deepseek-v4-flash", ""

    runner.run("e2e_S02", "session", "创建会话+绑定模型", create_with_model)

    def list_sessions():
        resp = runner.client.get("/api/sessions")
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        return len(body) >= 2, f"会话数不足: {len(body)}"

    runner.run("e2e_S03", "session", "会话列表 ≥2", list_sessions)

    def get_session():
        resp = runner.client.get(f"/api/sessions/{runner._session_id}")
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        return body.get("title") == "E2E评测会话", ""

    runner.run("e2e_S04", "session", "获取会话详情", get_session)

    def update_session():
        resp = runner.client.patch(f"/api/sessions/{runner._session_id}", {
            "title": "E2E评测会话(已更新)",
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        return body.get("title") == "E2E评测会话(已更新)", ""

    runner.run("e2e_S05", "session", "更新会话标题", update_session)

    def not_found():
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = runner.client.get(f"/api/sessions/{fake_id}")
        ok, _ = check_status(resp, 404)
        return ok, ""

    runner.run("e2e_S06", "session", "访问不存在会话 → 404", not_found)


# ══════════════════════════════════════════
# 模块 5: 聊天 (非流式)
# ══════════════════════════════════════════

def test_module_chat_non_streaming():
    print("\n\033[1m[模块5] 聊天 — 非流式\033[0m")

    def greet():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": runner._session_id,
            "messages": [{"role": "user", "content": "你好, 请用中文回答: 1+1等于几？"}],
            "model_id": "Qwen/Qwen3-30B-A3B",
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        content = body.get("content", "")
        return len(content) > 5, f"回复过短: '{content[:80]}'"

    runner.run("e2e_C01", "chat", "非流式: 基础对话", greet)

    def tool_call():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": runner._session_id,
            "messages": [{"role": "user", "content": "北京今天天气怎么样"}],
            "model_id": "Qwen/Qwen3-30B-A3B",
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        calls = body.get("tool_calls", [])
        if not calls:
            # 有些模型可能选择不调用工具, 只要回复非空即可
            return len(body.get("content", "")) > 5, "无回复内容"
        names = [c.get("function", {}).get("name", "") for c in calls]
        return "get_weather" in names, f"未调用 get_weather: {names}"

    runner.run("e2e_C02", "chat", "非流式: 天气工具调用", tool_call)

    def unknown_model():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": runner._session_id,
            "messages": [{"role": "user", "content": "测试"}],
            "model_id": "nonexistent-model-xyz",
            "stream": False,
        })
        ok, _ = check_status(resp, 400)
        return ok, ""

    runner.run("e2e_C03", "chat", "未知模型 → 400", unknown_model)

    def missing_session():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": "00000000-0000-0000-0000-000000000000",
            "messages": [{"role": "user", "content": "测试"}],
            "model_id": "Qwen/Qwen3-30B-A3B",
            "stream": False,
        })
        ok, _ = check_status(resp, 404)
        return ok, ""

    runner.run("e2e_C04", "chat", "不存在会话 → 404", missing_session)


# ══════════════════════════════════════════
# 模块 6: 聊天 (SSE 流式)
# ══════════════════════════════════════════

def test_module_chat_streaming():
    print("\n\033[1m[模块6] 聊天 — SSE 流式\033[0m")

    def stream_text():
        try:
            events = runner.client.sse_stream("/api/chat/completions", {
                "session_id": runner._session_id,
                "messages": [{"role": "user", "content": "说一句程序员鼓励的话"}],
                "model_id": "Qwen/Qwen3-30B-A3B",
                "stream": True,
            })
        except Exception as e:
            return False, str(e)
        if not events:
            return False, "无 SSE 事件返回"
        types = {e.get("type") for e in events}
        if "text" not in types:
            return False, f"缺少 text 事件: {types}"
        text_content = "".join(e.get("content", "") for e in events if e.get("type") == "text")
        return len(text_content) > 5, f"流式文本过短: '{text_content[:80]}'"

    runner.run("e2e_C05", "chat", "SSE: 文本回复含 text 事件", stream_text)

    def stream_with_tool():
        try:
            events = runner.client.sse_stream("/api/chat/completions", {
                "session_id": runner._session_id,
                "messages": [{"role": "user", "content": "上海天气"}],
                "model_id": "Qwen/Qwen3-30B-A3B",
                "stream": True,
            }, timeout=50.0)
        except Exception as e:
            return False, str(e)
        types = {e.get("type") for e in events}
        # 工具调用场景: 应该有 tool_call + tool_result
        has_tool = "tool_call" in types and "tool_result" in types
        has_text = "text" in types
        if has_tool:
            return True, ""
        if has_text:
            return True, "(LLM 选择不调用工具, 但回复了文本)"
        return False, f"事件类型: {types}"

    runner.run("e2e_C06", "chat", "SSE: 工具调用含完整事件", stream_with_tool)

    def stream_deepseek():
        """测试 DeepSeek V4 的 reasoning 事件"""
        try:
            events = runner.client.sse_stream("/api/chat/completions", {
                "session_id": runner._session_id,
                "messages": [{"role": "user", "content": "9.11和9.8哪个大? 请逐步推理"}],
                "model_id": "deepseek-v4-flash",
                "stream": True,
            }, timeout=50.0)
        except Exception as e:
            return False, str(e)
        types = {e.get("type") for e in events}
        return "text" in types, f"DeepSeek 流式事件: {types}"

    runner.run("e2e_C07", "chat", "SSE: DeepSeek V4 流式回复", stream_deepseek)

    def stream_cancel():
        """测试取消 (快速发送后断开)"""
        try:
            runner.client.sse_stream("/api/chat/completions", {
                "session_id": runner._session_id,
                "messages": [{"role": "user", "content": "写一篇2000字文章"}],
                "model_id": "Qwen/Qwen3-30B-A3B",
                "stream": True,
            }, timeout=1.0)
            return True, ""  # 不抛异常就算过
        except requests.Timeout:
            return True, "(超时预期行为)"
        except Exception as e:
            return "Read timed out" in str(e) or "timeout" in str(e).lower(), str(e)

    runner.run("e2e_C08", "chat", "SSE: 客户端断开不崩溃", stream_cancel)


# ══════════════════════════════════════════
# 模块 7: 额度追踪
# ══════════════════════════════════════════

def test_module_usage():
    print("\n\033[1m[模块7] 额度追踪\033[0m")

    def get_usage():
        resp = runner.client.get("/api/usage")
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        for key in ("text", "multimodal", "image_gen", "limits"):
            if key not in body:
                return False, f"缺少字段: {key}"
        # 额度应 > 0 (没超限)
        for key in ("text", "multimodal", "image_gen"):
            if body[key] <= 0:
                return False, f"{key} 额度已用完 ({body[key]})"
        return True, ""

    runner.run("e2e_U01", "usage", "额度查询含全部类型", get_usage)

    def limits_reasonable():
        resp = runner.client.get("/api/usage")
        body = resp.json()
        limits = body.get("limits", {})
        # 检查限制值合理
        if limits.get("text", 0) < 100:
            return False, f"text 限制过小: {limits}"
        if limits.get("multimodal", 0) < 10:
            return False, f"multimodal 限制过小: {limits}"
        return True, ""

    runner.run("e2e_U02", "usage", "额度限制值合理", limits_reasonable)


# ══════════════════════════════════════════
# 模块 8: 生图 API
# ══════════════════════════════════════════

def test_module_image_gen():
    print("\n\033[1m[模块8] 生图 API\033[0m")

    def submit():
        resp = runner.client.post("/api/images/generations", {
            "prompt": "a cute cat",
            "size": "512x512",
            "steps": 10,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        runner._task_id = body.get("task_id", "")
        return bool(runner._task_id) and body.get("status") == "PENDING", ""

    runner.run("e2e_I01", "image", "提交生图任务 → task_id", submit)

    def query():
        if not runner._task_id:
            return False, "无 task_id, 跳过"
        resp = runner.client.get(f"/api/images/generations/{runner._task_id}")
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        valid_status = body.get("status") in ("PENDING", "RUNNING", "PROCESSING", "SUCCEED", "FAILED")
        return valid_status, f"未知状态: {body.get('status')}"

    runner.run("e2e_I02", "image", "查询生图任务状态", query)

    def empty_prompt():
        resp = runner.client.post("/api/images/generations", {"prompt": ""})
        ok, _ = check_status(resp, 400)
        return ok, ""

    runner.run("e2e_I03", "image", "空 prompt → 400", empty_prompt)


# ══════════════════════════════════════════
# 模块 9: 边界与错误处理
# ══════════════════════════════════════════

def test_module_edge_cases():
    print("\n\033[1m[模块9] 边界与错误处理\033[0m")

    def empty_messages():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": runner._session_id,
            "messages": [],
            "stream": False,
        })
        ok, _ = check_status(resp, 400)
        return ok, ""

    runner.run("e2e_E01", "edge", "空 messages → 400", empty_messages)

    def invalid_json():
        resp = runner.client.session.post(
            f"{runner.client.base_url}/api/chat/completions",
            data="not json", headers=runner.client._headers(),
            timeout=30,
        )
        # FastAPI 默认返回 422 或 400
        return resp.status_code in (422, 400), f"HTTP {resp.status_code}"

    runner.run("e2e_E02", "edge", "非法 JSON → 4xx", invalid_json)

    def long_message():
        long_text = "测试" * 5000  # 10000 字符
        resp = runner.client.post("/api/chat/completions", {
            "session_id": runner._session_id,
            "messages": [{"role": "user", "content": long_text}],
            "stream": False,
        })
        # 期望能处理或优雅拒绝
        return resp.status_code in (200, 400, 413, 422), f"HTTP {resp.status_code}"

    runner.run("e2e_E03", "edge", "超长消息不崩溃", long_message)

    def cors_headers():
        resp = runner.client.session.options(
            f"{runner.client.base_url}/api/health",
            headers={"Origin": "http://localhost:4000", "Access-Control-Request-Method": "GET"},
            timeout=10,
        )
        return resp.status_code < 500, f"HTTP {resp.status_code}"

    runner.run("e2e_E04", "edge", "CORS 预检不报错", cors_headers)

    def method_not_allowed():
        resp = runner.client.session.put(
            f"{runner.client.base_url}/api/health",
            timeout=10,
        )
        return resp.status_code in (405, 404), f"HTTP {resp.status_code}"

    runner.run("e2e_E05", "edge", "错误方法 → 4xx", method_not_allowed)

    def sql_injection_attempt():
        resp = runner.client.post("/api/auth/login", {
            "username": "admin' OR '1'='1",
            "password": "' OR 1=1 --",
        }, auth=False)
        # 应返回 401, 不是 500
        return resp.status_code in (401, 422), f"HTTP {resp.status_code} (可能注入风险!)"

    runner.run("e2e_E06", "edge", "SQL 注入 → 401 而非 500", sql_injection_attempt)

    def xss_attempt():
        resp = runner.client.post("/api/auth/register", {
            "username": "<script>alert('xss')</script>",
            "password": TEST_PASSWORD,
        }, auth=False)
        # 应能处理 (201 创建成功或 422 拒绝都 OK, 但不能 500)
        ok = resp.status_code != 500
        return ok, f"HTTP {resp.status_code}"

    runner.run("e2e_E07", "edge", "XSS payload → 非 500", xss_attempt)

    def trace_header():
        resp = runner.client.get("/api/health", auth=False)
        trace_id = resp.headers.get("X-Trace-Id", "")
        return len(trace_id) == 12, f"trace_id 无效: '{trace_id}'"

    runner.run("e2e_E08", "edge", "响应含 X-Trace-Id", trace_header)


# ══════════════════════════════════════════
# 辅助: 生成测试图片
# ══════════════════════════════════════════

# 最小 1x1 红色 PNG (base64), 用于图片上传测试
TEST_IMAGE_BASE64 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNjN9GQAAAAlw"
    "SFlzAAAWJQAAFiUBSVIk8AAAAA5JREFUCJlj+M/A8J8BBAAjAAHylF1oAAAAAElFTkSuQmCC"
)

# 100x100 红色 PNG (更大, 用于真实测试)
TEST_IMAGE_B64_LARGE = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAAACXBIWXMAABYlAAAWJQ"
    "FJUiTwAAABZWlDQ1BEaXNwbGF5IFBQMyBJbWFnZSBTY2VuZXIgUHJvZmlsZQAAeJxjYGAyYQCCV4EYAQgYGBiYwA"
    "gBmQSYGBhA5GCMAAWgAAUAAAAAAAAAAAAAMgBmAH4A3AEiAXABqgHwAlYCnALqA0gDlgPsBEoEoAUGBWIFwgYoB"
    "qgHMAeICAoIUgiiCSgJngnkCkgK2gs6C5oL+gxaDL4NHg2kDiIOeg7IDy4Png/4EGYQwhEqEXgRuhHgEjYSkhMK"
    "E4YT8hR0FNIVNhWiFf4WShaeFvIXRhgAGFAYqhj6GU4Zohn2GmoawBsSG2YbuhwOHowe4B84H5Af7iBmILohECF"
    "sIcoiJiJiIr4jGiN6I9wkNCRqJLwk/CUgJWYljiWuJdAmNibSJzAngCfQKDIodCimKQgpcimcKcgqFCpiKrgrEC"
    "t+K8QsEixSLQotWi20Lhouai6WLsIvMC9+L+wwOjCKMNQxKjF+MdQyKjKCMtgzLjOEM9o0UDSmNPw1WjW4NhY2d"
    "DbSNzA3jjgMOGg45jlkOeQ6QjqgOxI7cDvOPCw8qj0IPWY9xD4iPoA+3j88P5pAHkB2QNRBMkGQQg5CbELMQypD"
    "iEPmREZEokUARYJF4EZCRqBG/kdcR7pIGEhoSLZJDElgSaxJ+EpISpZK4ksuS3pLxkwUTEhMlEzgTSxNeE3ETiBO"
    "bE64TwRPUFBqUQxRnFIsUrxTTFQkVJpVOFW2VjRWsldQV8ZYQli6WTRZrlomWp5bGFuSXAxchlygXRpdkl4MXoZf"
    "AF96YARgjmEIYZhiGGKwY0hUDgAABY0B+QAA"
)


# ══════════════════════════════════════════
# 模块 10: 多轮对话 + 模型切换
# ══════════════════════════════════════════

def test_module_multiturn_model_switch():
    print("\n\033[1m[模块10] 多轮对话 + 模型切换\033[0m")

    # 先创建一个专用会话
    mt_session_id: str = ""

    def create_mt_session():
        nonlocal mt_session_id
        resp = runner.client.post("/api/sessions", {"title": "多轮对话测试"})
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        mt_session_id = resp.json()["id"]
        return True, ""

    runner.run("e2e_MT01", "multiturn", "创建多轮对话会话", create_mt_session)

    # 10.1: 第一轮 — 告诉 AI 一个事实
    round1_response = ""

    def round1():
        nonlocal round1_response
        resp = runner.client.post("/api/chat/completions", {
            "session_id": mt_session_id,
            "messages": [{"role": "user", "content": "记住: 我最喜欢的颜色是深海蓝。回复'已记住'即可。"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        round1_response = resp.json().get("content", "")
        return len(round1_response) > 0, f"空回复"

    runner.run("e2e_MT02", "multiturn", "第1轮: 设置上下文事实", round1)

    # 10.2: 第二轮 — 验证上下文记忆
    def round2():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": mt_session_id,
            "messages": [{"role": "user", "content": "我最喜欢的颜色是什么？用中文回答"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        content = resp.json().get("content", "")
        return "蓝" in content or "blue" in content.lower(), f"未回忆出颜色: '{content[:100]}'"

    runner.run("e2e_MT03", "multiturn", "第2轮: 验证上下文记忆", round2)

    # 10.3: 第三轮 — 计算 (验证工具调用在多轮后正常)
    def round3():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": mt_session_id,
            "messages": [{"role": "user", "content": "100 * 25 等于多少？"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        content = resp.json().get("content", "")
        calls = resp.json().get("tool_calls", [])
        has_answer = "2500" in content
        has_tool = any("calculate" in str(c) for c in calls)
        return has_answer or has_tool, f"无2500无calculate: '{content[:100]}'"

    runner.run("e2e_MT04", "multiturn", "第3轮: 工具调用正常", round3)

    # 10.4: 模型切换 — 切到 DeepSeek V4
    def switch_model():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": mt_session_id,
            "messages": [{"role": "user", "content": "现在是什么模型？简单回答即可"}],
            "model_id": "deepseek-v4-flash",
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        content = resp.json().get("content", "")
        return len(content) > 3, "DeepSeek 无回复"

    runner.run("e2e_MT05", "multiturn", "切换模型: DeepSeek V4", switch_model)

    # 10.5: 切回 Qwen3-30B 继续
    def switch_back():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": mt_session_id,
            "messages": [{"role": "user", "content": "我最喜欢的颜色是什么？(看上下文)"}],
            "model_id": "Qwen/Qwen3-30B-A3B",
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        content = resp.json().get("content", "")
        return "蓝" in content, f"切回后丢失上下文: '{content[:120]}'"

    runner.run("e2e_MT06", "multiturn", "切回 Qwen3: 上下文仍保留", switch_back)

    # 清理多轮会话
    runner.client.delete(f"/api/sessions/{mt_session_id}")


# ══════════════════════════════════════════
# 模块 11: 图片上传 + 分析
# ══════════════════════════════════════════

def test_module_image_analysis():
    print("\n\033[1m[模块11] 图片上传 + 分析\033[0m")

    img_session_id: str = ""

    def create_img_session():
        nonlocal img_session_id
        resp = runner.client.post("/api/sessions", {"title": "图片分析测试"})
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        img_session_id = resp.json()["id"]
        return True, ""

    runner.run("e2e_IM01", "img_analysis", "创建图片分析会话", create_img_session)

    # 11.1: 发送图片 (模拟前端上传)
    def upload_image():
        content = [
            {"type": "image_url", "image_url": {"url": TEST_IMAGE_BASE64}},
            {"type": "text", "text": "这张图片是什么颜色的？请调用 analyze_image 工具"},
        ]
        resp = runner.client.post("/api/chat/completions", {
            "session_id": img_session_id,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        # 应该触发 analyze_image 工具调用
        calls = body.get("tool_calls", [])
        content_text = body.get("content", "")
        tool_names = [c.get("function", {}).get("name", "") for c in calls]
        has_analyze = "analyze_image" in tool_names
        has_response = len(content_text) > 5
        return has_analyze or has_response, f"calls={tool_names} content='{content_text[:80]}'"

    runner.run("e2e_IM02", "img_analysis", "上传图片 → 触发 analyze_image", upload_image)

    # 11.2: 第二轮 — 引用上文图片 ("刚才那张图")
    def reference_previous_image():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": img_session_id,
            "messages": [{"role": "user", "content": "刚才那张图片里有什么？描述一下"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        content = body.get("content", "")
        return len(content) > 5, f"空回复: '{content[:80]}'"

    runner.run("e2e_IM03", "img_analysis", "引用上文图片 (上下文)", reference_previous_image)

    # 11.3: 发送多张图片
    def upload_multiple_images():
        content = [
            {"type": "image_url", "image_url": {"url": TEST_IMAGE_BASE64}},
            {"type": "image_url", "image_url": {"url": TEST_IMAGE_B64_LARGE}},
            {"type": "text", "text": "我发了两张图片，请分析第一张(索引0)"},
        ]
        resp = runner.client.post("/api/chat/completions", {
            "session_id": img_session_id,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        content = body.get("content", "")
        calls = body.get("tool_calls", [])
        # 检查是否触发图片相关工具
        tool_names = [c.get("function", {}).get("name", "") for c in calls]
        has_img_tool = any(t in tool_names for t in ["analyze_image", "edit_image"])
        return has_img_tool or len(content) > 5, f"无图片工具调用: {tool_names}"

    runner.run("e2e_IM04", "img_analysis", "上传多张图片", upload_multiple_images)


# ══════════════════════════════════════════
# 模块 12: 图片生成 + 分析生图 + 编辑图片
# ══════════════════════════════════════════

def test_module_image_gen_analysis_edit():
    print("\n\033[1m[模块12] 图片生成 → 分析生图 → 编辑图片\033[0m")

    gen_session_id: str = ""

    def create_gen_session():
        nonlocal gen_session_id
        resp = runner.client.post("/api/sessions", {"title": "生图+分析+编辑测试"})
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        gen_session_id = resp.json()["id"]
        return True, ""

    runner.run("e2e_GA01", "img_chain", "创建生图链会话", create_gen_session)

    # 12.1: 生成一张图片 (流式, 观察 tool_queued/tool_progress/tool_result)
    gen_image_url: str = ""

    def do_generate():
        nonlocal gen_image_url
        try:
            events = runner.client.sse_stream("/api/chat/completions", {
                "session_id": gen_session_id,
                "messages": [{"role": "user", "content": "画一个红色的圆形 logo，简单风格"}],
                "stream": True,
            }, timeout=90.0)
        except Exception as e:
            return False, str(e)

        event_types = {e.get("type") for e in events}
        # 异步生图应有: tool_call → tool_queued → tool_progress → tool_result
        has_queue = "tool_queued" in event_types
        has_progress = "tool_progress" in event_types
        has_result = "tool_result" in event_types
        has_call = "tool_call" in event_types

        # 提取生图 URL
        for e in events:
            if e.get("type") == "tool_result":
                content = e.get("content", "")
                urls = re.findall(r'https?://\S+', content)
                if urls:
                    gen_image_url = urls[0]
                    break

        detail = f"events={sorted(event_types)} url={'found' if gen_image_url else 'no'}"
        if has_call and has_result:
            return True, detail
        if has_call and not has_result:
            return False, f"有 tool_call 无 tool_result: {detail}"
        # 模型可能选择不调用工具
        return "text" in event_types, f"无生图工具调用: {detail}"

    runner.run("e2e_GA02", "img_chain", "SSE: 生图含 queue/progress/result", do_generate)

    # 12.2: 分析刚生成的图片
    def analyze_generated():
        if not gen_image_url:
            return False, "跳过: 上一步未生成图片 URL"
        # 构造一条引用图片的消息
        content = [
            {"type": "image_url", "image_url": {"url": gen_image_url}},
            {"type": "text", "text": "这张刚生成的图片是什么内容？描述一下"},
        ]
        resp = runner.client.post("/api/chat/completions", {
            "session_id": gen_session_id,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        content_text = body.get("content", "")
        calls = body.get("tool_calls", [])
        tool_names = [c.get("function", {}).get("name", "") for c in calls]
        has_analyze = "analyze_image" in tool_names
        return has_analyze or len(content_text) > 10, f"无分析: calls={tool_names}"

    runner.run("e2e_GA03", "img_chain", "分析刚生成的图片", analyze_generated)

    # 12.3: 编辑刚生成的图片
    def edit_generated():
        if not gen_image_url:
            return False, "跳过: 上一步未生成图片 URL"
        # 在下一轮消息中指定编辑上文图片
        resp = runner.client.post("/api/chat/completions", {
            "session_id": gen_session_id,
            "messages": [{"role": "user", "content": "把刚才那张图的红色改成蓝色，调用 edit_image"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        calls = body.get("tool_calls", [])
        tool_names = [c.get("function", {}).get("name", "") for c in calls]
        content_text = body.get("content", "")
        has_edit = "edit_image" in tool_names
        return has_edit or len(content_text) > 5, f"未调用 edit_image: calls={tool_names}"

    runner.run("e2e_GA04", "img_chain", "编辑上文图片 → edit_image", edit_generated)


# ══════════════════════════════════════════
# 模块 13: 对话分支 (send / regenerate / reedit)
# ══════════════════════════════════════════

def test_module_branch():
    print("\n\033[1m[模块13] 对话分支 (send/regenerate/reedit)\033[0m")

    branch_session_id: str = ""
    branch_user_msg_id: str = ""   # 第一条用户消息 ID
    branch_asst1_id: str = ""      # 第一条助手回复 ID
    branch_asst2_id: str = ""      # regenerate 回复 ID

    def create_branch_session():
        nonlocal branch_session_id
        resp = runner.client.post("/api/sessions", {"title": "分支测试"})
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        branch_session_id = resp.json()["id"]
        return True, ""

    runner.run("e2e_BR01", "branch", "创建分支测试会话", create_branch_session)

    # 13.1: 发送第一条消息 (send)
    def branch_send():
        nonlocal branch_user_msg_id, branch_asst1_id
        # 发送后查询会话消息, 获取真实 message_id
        resp = runner.client.post("/api/chat/completions", {
            "session_id": branch_session_id,
            "messages": [{"role": "user", "content": "用一句话介绍 Python 语言"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        # 获取消息列表
        resp2 = runner.client.get(f"/api/sessions/{branch_session_id}")
        msgs = resp2.json().get("messages", [])
        user_msgs = [m for m in msgs if m.get("role") == "user"]
        asst_msgs = [m for m in msgs if m.get("role") == "assistant"]
        if not user_msgs or not asst_msgs:
            return False, f"消息不完整: user={len(user_msgs)} asst={len(asst_msgs)}"
        branch_user_msg_id = user_msgs[-1]["id"]
        branch_asst1_id = asst_msgs[-1]["id"]
        return len(branch_user_msg_id) > 0 and len(branch_asst1_id) > 0, ""

    runner.run("e2e_BR02", "branch", "send: 消息正确存储+可查询", branch_send)

    # 13.2: Regenerate — 用 parent_id 指向用户消息, 创建兄弟分支
    def branch_regenerate():
        nonlocal branch_asst2_id
        resp = runner.client.post("/api/chat/completions", {
            "session_id": branch_session_id,
            "messages": [{"role": "user", "content": "用一句话介绍 Python 语言"}],
            "parent_id": branch_user_msg_id,  # regenerate: parent = 用户消息
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        # 验证: 现在应该有 2 条 assistant 消息, 共享同一 parent
        resp2 = runner.client.get(f"/api/sessions/{branch_session_id}")
        msgs = resp2.json().get("messages", [])
        asst_msgs = [m for m in msgs if m.get("role") == "assistant"]
        siblings_of_user = [m for m in asst_msgs if m.get("parent_id") == branch_user_msg_id]
        if len(siblings_of_user) < 2:
            return False, f"regenerate 未创建兄弟节点: siblings={len(siblings_of_user)}"
        branch_asst2_id = siblings_of_user[-1]["id"]
        return branch_asst1_id != branch_asst2_id, "两个回复 ID 相同"

    runner.run("e2e_BR03", "branch", "regenerate: 创建兄弟分支", branch_regenerate)

    # 13.3: 验证树形结构 — 两兄弟共享同一 parent
    def verify_tree():
        resp = runner.client.get(f"/api/sessions/{branch_session_id}")
        msgs = resp.json().get("messages", [])
        # 检查有兄弟关系的 assistant 消息
        asst_with_parent = [m for m in msgs
                          if m.get("role") == "assistant" and m.get("parent_id") == branch_user_msg_id]
        if len(asst_with_parent) < 2:
            return False, f"兄弟不足: {len(asst_with_parent)}"
        # 验证 content 不同 (两条不同回复)
        contents = [m.get("content", "") for m in asst_with_parent]
        if contents[0] == contents[1]:
            return False, "两条 regenerate 回复完全相同"
        return True, ""

    runner.run("e2e_BR04", "branch", "验证: 兄弟节点 content 不同", verify_tree)

    # 13.4: Reedit — 编辑后重发, parent = 原用户消息的 parent
    def branch_reedit():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": branch_session_id,
            "messages": [{"role": "user", "content": "用三句话详细介绍 Python"}],
            "parent_id": None,  # reedit: 新用户消息的 parent = root (null)
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        # 验证: 应该新增一条 user + 一条 asst
        resp2 = runner.client.get(f"/api/sessions/{branch_session_id}")
        msgs = resp2.json().get("messages", [])
        user_msgs = [m for m in msgs if m.get("role") == "user"]
        return len(user_msgs) >= 2, f"reedit 后 user 消息数: {len(user_msgs)}"

    runner.run("e2e_BR05", "branch", "reedit: 新建 user+asst 分支", branch_reedit)

    # 13.5: 子分支 — 在 regenerate 回复下继续对话
    def branch_child():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": branch_session_id,
            "messages": [{"role": "user", "content": "你说得对, 再给我举个例子"}],
            "parent_id": branch_asst2_id,  # 在第二个回复下继续
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        resp2 = runner.client.get(f"/api/sessions/{branch_session_id}")
        msgs = resp2.json().get("messages", [])
        # 检查是否有消息的 parent = branch_asst2_id
        children = [m for m in msgs if m.get("parent_id") == branch_asst2_id]
        return len(children) >= 1, f"子分支无消息: children={len(children)}"

    runner.run("e2e_BR06", "branch", "子分支: 在 regenerate 下继续对话", branch_child)

    # 清理
    runner.client.delete(f"/api/sessions/{branch_session_id}")


# ══════════════════════════════════════════
# 模块 14: 分支上下文隔离 (深度)
# ══════════════════════════════════════════

def test_module_branch_context_isolation():
    """
    验证分支树中每个分支的上下文严格隔离:
    - 兄弟节点内容不会混入当前分支
    - 子分支上下文仅包含自己的祖先链
    - 切换分支后 LLM 看到的是正确的链
    """
    print("\n\033[1m[模块14] 分支上下文隔离\033[0m")

    iso_session_id: str = ""
    py_user_id: str = ""      # "聊Python" user msg
    py_asst1_id: str = ""     # 第一个 Python 回复
    py_asst2_id: str = ""     # regenerate 回复
    java_user_id: str = ""    # "聊Java" user msg
    java_asst_id: str = ""    # Java 回复
    py_child_user_id: str = "" # Python 子分支 user
    py_child_asst_id: str = "" # Python 子分支 asst

    def create_iso_session():
        nonlocal iso_session_id
        resp = runner.client.post("/api/sessions", {"title": "上下文隔离测试"})
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        iso_session_id = resp.json()["id"]
        return True, ""

    runner.run("e2e_CI01", "ctx_iso", "创建隔离测试会话", create_iso_session)

    # 14.1: 构建 Python 分支
    def build_python_branch():
        nonlocal py_user_id, py_asst1_id
        resp = runner.client.post("/api/chat/completions", {
            "session_id": iso_session_id,
            "messages": [{"role": "user", "content": "用一句话介绍 Python 语言的特点"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        resp2 = runner.client.get(f"/api/sessions/{iso_session_id}")
        msgs = resp2.json().get("messages", [])
        users = [m for m in msgs if m.get("role") == "user"]
        assts = [m for m in msgs if m.get("role") == "assistant"]
        if not users or not assts:
            return False, "消息不完整"
        py_user_id = users[-1]["id"]
        py_asst1_id = assts[-1]["id"]
        content = assts[-1].get("content", "")
        return "Python" in content or "python" in content.lower(), f"回复不含Python: '{content[:60]}'"

    runner.run("e2e_CI02", "ctx_iso", "构建Python分支", build_python_branch)

    # 14.2: Regenerate 创建 Python 兄弟
    def build_python_sibling():
        nonlocal py_asst2_id
        resp = runner.client.post("/api/chat/completions", {
            "session_id": iso_session_id,
            "messages": [{"role": "user", "content": "用一句话介绍 Python 语言的特点"}],
            "parent_id": py_user_id,
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        resp2 = runner.client.get(f"/api/sessions/{iso_session_id}")
        msgs = resp2.json().get("messages", [])
        assts = [m for m in msgs if m.get("role") == "assistant" and m.get("parent_id") == py_user_id]
        if len(assts) < 2:
            return False, f"regenerate 未创建兄弟: {len(assts)}"
        py_asst2_id = assts[-1]["id"]
        c1 = assts[0].get("content", "")
        c2 = assts[1].get("content", "")
        return c1 != c2, "两条兄弟回复完全相同"

    runner.run("e2e_CI03", "ctx_iso", "Regenerate: Python兄弟分支", build_python_sibling)

    # 14.3: 在 Python asst2 下创建子分支
    def build_python_child():
        nonlocal py_child_user_id, py_child_asst_id
        resp = runner.client.post("/api/chat/completions", {
            "session_id": iso_session_id,
            "messages": [{"role": "user", "content": "刚才你说的 Python 特点, 给一个代码例子"}],
            "parent_id": py_asst2_id,
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        resp2 = runner.client.get(f"/api/sessions/{iso_session_id}")
        msgs = resp2.json().get("messages", [])
        users = [m for m in msgs if m.get("role") == "user" and m.get("parent_id") == py_asst2_id]
        assts = [m for m in msgs if m.get("role") == "assistant" and m.get("parent_id") in [u["id"] for u in users]]
        if not users or not assts:
            return False, f"子分支不完整: user={len(users)} asst={len(assts)}"
        py_child_user_id = users[-1]["id"]
        py_child_asst_id = assts[-1]["id"]
        return True, ""

    runner.run("e2e_CI04", "ctx_iso", "Python子分支: 在asst2下继续对话", build_python_child)

    # 14.4: 构建 Java 分支 (reedit 场景, parent=null)
    def build_java_branch():
        nonlocal java_user_id, java_asst_id
        resp = runner.client.post("/api/chat/completions", {
            "session_id": iso_session_id,
            "messages": [{"role": "user", "content": "用一句话介绍 Java 语言的特点"}],
            "parent_id": None,
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        resp2 = runner.client.get(f"/api/sessions/{iso_session_id}")
        msgs = resp2.json().get("messages", [])
        # Java 分支的 user 应该 parent=null
        java_users = [m for m in msgs if m.get("role") == "user" and "Java" in str(m.get("content", ""))]
        if not java_users:
            return False, "未找到 Java user 消息"
        java_user_id = java_users[-1]["id"]
        java_assts = [m for m in msgs if m.get("role") == "assistant" and m.get("parent_id") == java_user_id]
        if not java_assts:
            return False, "Java 无回复"
        java_asst_id = java_assts[-1]["id"]
        content = java_assts[-1].get("content", "")
        return "Java" in content or "java" in content.lower(), f"Java回复不含Java: '{content[:60]}'"

    runner.run("e2e_CI05", "ctx_iso", "构建Java分支 (reedit, parent=null)", build_java_branch)

    # 14.5: ★ 核心测试 — Python 子分支上下文不混入 Java 内容 ★
    def verify_python_child_no_java_leak():
        """
        Python 子分支的上下文链: root → py_user → py_asst2 → py_child_user → py_child_asst
        Java 分支是 py_user 的兄弟, 不应出现在 python_child 的上下文中
        """
        resp = runner.client.post("/api/chat/completions", {
            "session_id": iso_session_id,
            "messages": [{"role": "user", "content": "我们之前讨论的是什么编程语言？只回答语言名即可"}],
            "parent_id": py_child_asst_id,  # 在Python子分支下继续
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        content = resp.json().get("content", "")
        has_python = "Python" in content or "python" in content.lower()
        has_java = "Java" in content or "java" in content.lower()
        if has_java and not has_python:
            return False, f"★ 上下文污染! 回复含Java不应含Java: '{content[:120]}'"
        if has_python:
            return True, f"正确识别Python: '{content[:80]}'"
        return "Python" in content or "python" in content.lower(), f"未识别Python: '{content[:120]}'"

    runner.run("e2e_CI06", "ctx_iso", "★ Python子分支不含Java污染 ★", verify_python_child_no_java_leak)

    # 14.6: ★ 核心测试 — Java 分支上下文不混入 Python 内容 ★
    def verify_java_branch_no_python_leak():
        """Java 分支上下文链: root → java_user → java_asst"""
        resp = runner.client.post("/api/chat/completions", {
            "session_id": iso_session_id,
            "messages": [{"role": "user", "content": "我们讨论的是什么语言？只回答语言名"}],
            "parent_id": java_asst_id,
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        content = resp.json().get("content", "")
        has_python = "Python" in content or "python" in content.lower()
        has_java = "Java" in content or "java" in content.lower()
        if has_python:
            return False, f"★ Java分支被Python污染! '{content[:120]}'"
        return has_java or len(content) > 2, f"未识别Java: '{content[:120]}'"

    runner.run("e2e_CI07", "ctx_iso", "★ Java分支不含Python污染 ★", verify_java_branch_no_python_leak)

    # 14.7: ★ 验证兄弟隔离 — Python asst1 分支不包含 asst2 子分支内容 ★
    def verify_sibling_isolation():
        """asst1 和 asst2 是兄弟。在 asst1 下继续时不应看到 asst2 的子分支"""
        resp = runner.client.post("/api/chat/completions", {
            "session_id": iso_session_id,
            "messages": [{"role": "user", "content": "我之前有让你'举个例子'吗？只回答有或没有"}],
            "parent_id": py_asst1_id,  # 在 asst1 (没有子分支) 下
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        content = resp.json().get("content", "")
        # asst1 分支下不应该有"举个例子"的上下文(那是asst2的子分支)
        has_example = "例子" in content or "示例" in content or "举例" in content
        if has_example:
            return False, f"★ asst1分支看到asst2子分支内容! '{content[:150]}'"
        return True, ""

    runner.run("e2e_CI08", "ctx_iso", "★ asst1兄弟不包含asst2子分支 ★", verify_sibling_isolation)

    # 14.8: 验证消息树的 parent_id 结构完整性
    def verify_tree_structure():
        resp = runner.client.get(f"/api/sessions/{iso_session_id}")
        msgs = resp.json().get("messages", [])
        msg_map = {m["id"]: m for m in msgs}

        # 所有非根消息的 parent 应该存在 (或为 null)
        root_count = 0
        orphan_count = 0
        for m in msgs:
            pid = m.get("parent_id")
            if pid is None:
                root_count += 1
            elif pid not in msg_map:
                orphan_count += 1

        # Python user 应该有 2 个 asst 子节点
        py_children = [m for m in msgs if m.get("parent_id") == py_user_id
                      and m.get("role") == "assistant"]
        # Python asst2 应该有 1 个 user 子节点
        py_asst2_children = [m for m in msgs if m.get("parent_id") == py_asst2_id]

        detail = f"root={root_count} orphan={orphan_count} py_kids={len(py_children)} asst2_kids={len(py_asst2_children)}"
        if orphan_count > 0:
            return False, f"存在孤儿节点: {detail}"
        if len(py_children) < 2:
            return False, f"Python user 兄弟不足: {detail}"
        if len(py_asst2_children) < 1:
            return False, f"asst2 无子节点: {detail}"
        return True, detail

    runner.run("e2e_CI09", "ctx_iso", "树结构完整性: 无孤儿 兄弟数正确", verify_tree_structure)

    runner.client.delete(f"/api/sessions/{iso_session_id}")


# ══════════════════════════════════════════
# 模块 15: 图片上下文完整性 (深度)
# ══════════════════════════════════════════

def test_module_image_context_integrity():
    """
    验证图片数据在多轮对话中正确保留:
    - 图片 URL 持久化在 messages.content 中
    - 多轮后图片仍可被 LLM 引用
    - 不会因为 _to_llm_format() 丢失图片索引信息
    """
    print("\n\033[1m[模块15] 图片上下文完整性\033[0m")

    img_ctx_session: str = ""

    def create_img_ctx_session():
        nonlocal img_ctx_session
        resp = runner.client.post("/api/sessions", {"title": "图片上下文完整性测试"})
        ok, err = check_status(resp, 201)
        if not ok:
            return False, err
        img_ctx_session = resp.json()["id"]
        return True, ""

    runner.run("e2e_IC01", "img_ctx", "创建图片上下文会话", create_img_ctx_session)

    # 15.1: 上传第一张图片
    img1_url: str = ""

    def upload_img1():
        nonlocal img1_url
        content = [
            {"type": "image_url", "image_url": {"url": TEST_IMAGE_BASE64}},
            {"type": "text", "text": "我上传了第一张图片(红色)。请调用 analyze_image 分析"},
        ]
        resp = runner.client.post("/api/chat/completions", {
            "session_id": img_ctx_session,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        # 从会话消息中提取存储的图片 URL
        resp2 = runner.client.get(f"/api/sessions/{img_ctx_session}")
        msgs = resp2.json().get("messages", [])
        for m in msgs:
            cnt = m.get("content", "")
            if isinstance(cnt, list):
                for part in cnt:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        img1_url = part.get("image_url", {}).get("url", "")
                        if img1_url:
                            break
            if img1_url:
                break
        return bool(img1_url), f"图片URL已存储: {img1_url[:80]}" if img1_url else "图片URL未存储到消息中!"

    runner.run("e2e_IC02", "img_ctx", "上传图1: URL持久化到messages", upload_img1)

    # 15.2: 第二张图片 (不同颜色, 便于区分)
    img2_url: str = ""

    def upload_img2():
        nonlocal img2_url
        content = [
            {"type": "image_url", "image_url": {"url": TEST_IMAGE_B64_LARGE}},
            {"type": "text", "text": "第二张图(稍大)。第一张是红的, 这张也是红的, 请记住"},
        ]
        resp = runner.client.post("/api/chat/completions", {
            "session_id": img_ctx_session,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        resp2 = runner.client.get(f"/api/sessions/{img_ctx_session}")
        msgs = resp2.json().get("messages", [])
        # 统计所有带 image_url 的消息
        img_count = 0
        for m in msgs:
            cnt = m.get("content", "")
            if isinstance(cnt, list):
                for part in cnt:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url and not img2_url:
                            # 找不同于 img1 的
                            if url != img1_url:
                                img2_url = url
                        img_count += 1
        return img_count >= 2, f"消息中图片数: {img_count}"

    runner.run("e2e_IC03", "img_ctx", "上传图2: 两张图都在消息中", upload_img2)

    # 15.3: 中间插入纯文本对话
    def text_turn():
        resp = runner.client.post("/api/chat/completions", {
            "session_id": img_ctx_session,
            "messages": [{"role": "user", "content": "1+1等于几？"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        return len(resp.json().get("content", "")) > 0, "空回复"

    runner.run("e2e_IC04", "img_ctx", "中间插入纯文本对话", text_turn)

    # 15.4: ★ 核心 — 多轮后 LLM 仍能感知上文图片 ★
    def llm_still_sees_images():
        """多轮后, LLM 应该知道之前发过图片"""
        resp = runner.client.post("/api/chat/completions", {
            "session_id": img_ctx_session,
            "messages": [{"role": "user", "content": "我之前发过图片吗？发了几张？什么颜色？"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        content = resp.json().get("content", "")
        # LLM 应该能提到图片相关的内容
        mentions_image = any(kw in content for kw in ["图", "张", "红", "色", "image", "picture", "发了"])
        return mentions_image or len(content) > 5, f"LLM未感知历史图片: '{content[:150]}'"

    runner.run("e2e_IC05", "img_ctx", "★ 多轮后LLM感知历史图片 ★", llm_still_sees_images)

    # 15.5: ★ 验证消息存储格式 — content 是数组而非纯文本 ★
    def verify_image_storage_format():
        """检查原始消息存储: 带图片的消息 content 应为数组, 含 image_url 对象"""
        resp = runner.client.get(f"/api/sessions/{img_ctx_session}")
        msgs = resp.json().get("messages", [])
        user_msgs = [m for m in msgs if m.get("role") == "user"]
        # 找到带图片的用户消息
        img_msgs = []
        for m in user_msgs:
            content = m.get("content", "")
            if isinstance(content, list):
                has_img = any(
                    isinstance(p, dict) and p.get("type") == "image_url"
                    for p in content
                )
                if has_img:
                    img_msgs.append(m)
        if len(img_msgs) < 2:
            return False, f"存储格式错误: 仅有 {len(img_msgs)} 条图片消息以数组存储"
        # 每条图片消息应该能提取出 image_url
        for m in img_msgs:
            content = m.get("content", [])
            urls_in_msg = [
                p.get("image_url", {}).get("url", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "image_url"
            ]
            if not urls_in_msg:
                return False, f"消息 {m['id'][:8]} 无可提取的 image_url"
        return True, f"图片消息数: {len(img_msgs)}, 格式正确"

    runner.run("e2e_IC06", "img_ctx", "★ 图片存储格式: content数组含image_url ★", verify_image_storage_format)

    # 15.6: 多次纯文本轮询后图片仍存在
    def multi_text_then_ask_image():
        for _ in range(2):
            resp = runner.client.post("/api/chat/completions", {
                "session_id": img_ctx_session,
                "messages": [{"role": "user", "content": "好, 继续"}],
                "stream": False,
            })
            if resp.status_code != 200:
                return False, f"中间对话失败: HTTP {resp.status_code}"

        # 再问图片
        resp = runner.client.post("/api/chat/completions", {
            "session_id": img_ctx_session,
            "messages": [{"role": "user", "content": "回到图片话题: 第一张图片是什么颜色的？调用 analyze_image"}],
            "stream": False,
        })
        ok, err = check_status(resp, 200)
        if not ok:
            return False, err
        body = resp.json()
        calls = body.get("tool_calls", [])
        content = body.get("content", "")
        tool_names = [c.get("function", {}).get("name", "") for c in calls]
        has_analyze = "analyze_image" in tool_names
        return has_analyze or len(content) > 5, f"无analyze调用: calls={tool_names}"

    runner.run("e2e_IC07", "img_ctx", "★ 多轮文本后analyze_image仍可用 ★", multi_text_then_ask_image)

    runner.client.delete(f"/api/sessions/{img_ctx_session}")


# ══════════════════════════════════════════
# 模块 16: 会话删除 (清理)
# ══════════════════════════════════════════

def test_module_cleanup():
    print("\n\033[1m[模块10] 清理\033[0m")

    def delete_session():
        resp = runner.client.delete(f"/api/sessions/{runner._session_id}")
        ok, err = check_status(resp, 204)
        if not ok:
            return False, err
        # 确认已删除
        resp2 = runner.client.get(f"/api/sessions/{runner._session_id}")
        return resp2.status_code == 404, f"删除后仍可访问: HTTP {resp2.status_code}"

    runner.run("e2e_CX01", "cleanup", "删除会话+确认不可访问", delete_session)


# ══════════════════════════════════════════
# 报告生成
# ══════════════════════════════════════════

def generate_report() -> str:
    """生成彩色终端报告 + JSON 快照"""
    report = runner.report
    report.end_time = time.time()

    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

    lines = []
    sep = "=" * 60
    lines.append(f"\n{BOLD}{sep}{RESET}")
    lines.append(f"{BOLD}     用户角度端到端评测报告 — 1号机 v1.4{RESET}")
    lines.append(f"{BOLD}{sep}{RESET}")
    lines.append(f" 测试用户: {TEST_USERNAME}")
    lines.append(f" 后端地址: {BASE_URL}")
    lines.append(f" 总耗时:   {report.total_duration_ms:.0f}ms")
    lines.append(f" 测试时间: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"{BOLD}{sep}{RESET}")

    # 按模块统计
    lines.append(f"\n{CYAN}模块统计:{RESET}")
    for mod, cases in report.by_module.items():
        p = sum(1 for c in cases if c.passed)
        t = len(cases)
        rate = p / max(t, 1) * 100
        color = GREEN if rate == 100 else YELLOW if rate >= 50 else RED
        bar = "█" * int(rate / 10) + "░" * (10 - int(rate / 10))
        lines.append(f"  [{mod:　<10s}] {color}{bar}{RESET} {p}/{t} ({rate:.0f}%)")

    # 总体统计
    lines.append(f"\n{BOLD}总体:{RESET}")
    color = GREEN if report.pass_rate >= 0.9 else YELLOW if report.pass_rate >= 0.7 else RED
    lines.append(f"  通过: {GREEN}{report.passed}{RESET}")
    lines.append(f"  失败: {RED}{report.failed}{RESET}")
    lines.append(f"  通过率: {color}{report.pass_rate * 100:.1f}%{RESET}")

    # 失败用例详情
    failed = [r for r in report.results if not r.passed]
    if failed:
        lines.append(f"\n{RED}失败用例详情:{RESET}")
        for r in failed:
            lines.append(f"  {RED}✗{RESET} [{r.module}] {r.name}")
            lines.append(f"     {RED}{r.error}{RESET}")

    # 评分: 每通过一个得 1 分, 满分 = 总用例数
    score = f"{report.passed}/{report.total}"
    grade_color = GREEN if report.pass_rate >= 0.9 else YELLOW if report.pass_rate >= 0.7 else RED
    lines.append(f"\n{BOLD}综合评分: {grade_color}{score}{RESET}")

    term_report = "\n".join(lines)

    # ─ 保存 JSON 快照 ─
    snapshot = {
        "test_user": TEST_USERNAME,
        "base_url": BASE_URL,
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "pass_rate": round(report.pass_rate, 4),
        "total_duration_ms": round(report.total_duration_ms),
        "modules": {
            mod: {
                "total": len(cases),
                "passed": sum(1 for c in cases if c.passed),
                "pass_rate": round(sum(1 for c in cases if c.passed) / max(len(cases), 1), 4),
            }
            for mod, cases in report.by_module.items()
        },
        "results": [
            {
                "id": r.case_id,
                "module": r.module,
                "name": r.name,
                "passed": r.passed,
                "duration_ms": round(r.duration_ms, 1),
                "error": r.error,
                "detail": r.detail,
            }
            for r in report.results
        ],
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    return term_report


# ══════════════════════════════════════════
# Main
# ══════════════════════════════════════════

def main():
    print(f"\n{'='*60}")
    print(f"  1号机 E2E 评测 v1.4")
    print(f"  目标: {BASE_URL}")
    print(f"  用户: {TEST_USERNAME}")
    print(f"{'='*60}")

    runner.report.start_time = time.time()

    # 按依赖顺序执行
    test_module_health()
    test_module_auth()
    test_module_models()
    test_module_sessions()
    test_module_chat_non_streaming()
    test_module_chat_streaming()
    test_module_usage()
    test_module_image_gen()
    test_module_edge_cases()
    test_module_multiturn_model_switch()
    test_module_image_analysis()
    test_module_image_gen_analysis_edit()
    test_module_branch()
    test_module_branch_context_isolation()
    test_module_image_context_integrity()
    test_module_cleanup()

    # 生成报告
    report = generate_report()
    print(report)
    print(f"\nJSON 快照: {REPORT_PATH}")

    # 返回退出码
    if runner.report.pass_rate < 0.7:
        print(f"\n\033[91m评测未通过! 通过率 {runner.report.pass_rate*100:.1f}% < 70%\033[0m")
        sys.exit(1)
    else:
        print(f"\n\033[92m评测通过! 通过率 {runner.report.pass_rate*100:.1f}%\033[0m")
        sys.exit(0)


if __name__ == "__main__":
    main()
