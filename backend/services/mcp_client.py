"""MCP Client — 连接外部 MCP 服务器，导入其工具到 Agent 工具列表"""
import json
import os
import subprocess
import sys
import threading
from backend.logger import get_logger

logger = get_logger("mcp.client")


class MCPExternalTool:
    """外部 MCP 工具的描述和调用入口"""

    def __init__(self, name: str, description: str, input_schema: dict,
                 server_name: str, process: subprocess.Popen | None = None):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.server_name = server_name
        self._process = process

    def to_openai_tool_def(self) -> dict:
        """转为 OpenAI function calling 格式的 tool_def"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"[MCP:{self.server_name}] {self.description}",
                "parameters": self.input_schema,
            },
        }

    def call(self, **kwargs) -> str:
        """通过 stdio 调用 MCP 工具 (简化版: JSON-RPC)"""
        if self._process is None or self._process.poll() is not None:
            return f"错误: MCP 服务器 {self.server_name} 已断开"

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": self.name,
                "arguments": kwargs,
            },
        }
        try:
            req_json = json.dumps(request, ensure_ascii=False) + "\n"
            self._process.stdin.write(req_json)
            self._process.stdin.flush()
            response_line = self._process.stdout.readline()
            if response_line:
                resp = json.loads(response_line)
                if "result" in resp:
                    content = resp["result"].get("content", [])
                    if content and isinstance(content, list):
                        return "\n".join(
                            c.get("text", str(c)) for c in content if isinstance(c, dict)
                        )
                    return str(content)
                elif "error" in resp:
                    return f"MCP 错误: {resp['error']}"
            return "MCP 调用: 无响应"
        except Exception as e:
            return f"MCP 调用失败: {e}"


class MCPToolManager:
    """管理外部 MCP 工具的发现和导入"""

    def __init__(self):
        self._servers: dict[str, subprocess.Popen] = {}
        self._tools: list[MCPExternalTool] = []
        self._config: list[dict] = []

    @property
    def config(self) -> list[dict]:
        return self._config

    def load_config(self, config_path: str = "") -> list[dict]:
        """从配置文件加载 MCP 服务器列表"""
        if not config_path:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "configs", "mcp_servers.json"
            )
        if not os.path.exists(config_path):
            logger.info(f"MCP 配置文件不存在: {config_path}")
            return []
        with open(config_path, "r", encoding="utf-8") as f:
            self._config = json.load(f)
        logger.info(f"加载了 {len(self._config)} 个 MCP 服务器配置")
        return self._config

    def connect_stdio(self, name: str, command: str, args: list[str]) -> list[MCPExternalTool]:
        """连接 stdio 模式 MCP 服务器，返回其工具列表。

        Windows 兼容: 对无扩展名的 command 自动追加 .cmd (如 npx -> npx.cmd)。
        补全 MCP 握手: initialize -> notifications/initialized -> tools/list。
        stderr 由 daemon 线程消费防止管道死锁。
        """
        logger.info(f"MCP连接: [{name}] 启动 {command} {' '.join(args)}")

        # Windows: CreateProcess 找不到无扩展名的命令 (如 npx), 自动加 .cmd
        exe = command
        if sys.platform == "win32" and not os.path.splitext(command)[1]:
            for ext in os.getenv("PATHEXT", "").split(os.pathsep):
                test = command + ext.lower()
                # 简单检查: 常见的是 .cmd/.bat
                if ext.lower() in (".cmd", ".bat", ".exe"):
                    exe = command + ext
                    break
            # 回退: 直接加 .cmd
            if exe == command:
                exe = command + ".cmd"

        proc = None
        try:
            try:
                proc = subprocess.Popen(
                    [exe] + args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
            except FileNotFoundError:
                logger.warning(f"MCP [{name}]: {exe} 未找到, 尝试 shell 模式")
                proc = subprocess.Popen(
                    [command] + args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    shell=True,
                )

            # 消费 stderr 防死锁
            _start_stderr_drain(proc, name)

            # === MCP 握手: initialize ===
            init_req = {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "AI-Agent-1号机", "version": "1.4"},
                },
            }
            proc.stdin.write(json.dumps(init_req, ensure_ascii=False) + "\n")
            proc.stdin.flush()

            init_raw = _readline_with_timeout(proc, timeout=30)
            if not init_raw:
                raise RuntimeError("MCP 服务器未响应 initialize")
            try:
                init_resp = json.loads(init_raw)
                if "error" in init_resp:
                    err = init_resp["error"]
                    raise RuntimeError(f"initialize 失败: {err.get('message', str(err))}")
            except json.JSONDecodeError as e:
                raise RuntimeError(f"initialize 响应非 JSON: {init_raw[:120]}")

            # === 发送 initialized 通知 ===
            proc.stdin.write(
                '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
            )
            proc.stdin.flush()

            # === tools/list ===
            list_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            }
            proc.stdin.write(json.dumps(list_req, ensure_ascii=False) + "\n")
            proc.stdin.flush()

            tools_raw = _readline_with_timeout(proc, timeout=30)
            if not tools_raw:
                raise RuntimeError("MCP 服务器未响应 tools/list")

            resp = json.loads(tools_raw)
            if "error" in resp:
                err = resp["error"]
                raise RuntimeError(f"tools/list 失败: {err.get('message', str(err))}")

            raw_tools = resp.get("result", {}).get("tools", [])

            tools = []
            for rt in raw_tools:
                tool = MCPExternalTool(
                    name=f"mcp_{name}_{rt.get('name', 'unknown')}",
                    description=rt.get("description", ""),
                    input_schema=rt.get("inputSchema", {"type": "object", "properties": {}}),
                    server_name=name,
                    process=proc,
                )
                tools.append(tool)

            self._servers[name] = proc
            self._tools.extend(tools)
            logger.info(f"MCP [{name}]: 导入 {len(tools)} 个工具")
            return tools

        except FileNotFoundError:
            logger.warning(f"MCP [{name}]: 命令未找到: {command}")
            if proc:
                _kill_proc(proc)
            return []
        except Exception as e:
            logger.error(f"MCP [{name}]: 连接失败: {e}")
            if proc:
                _kill_proc(proc)
            return []

    def get_all_tools(self) -> list[MCPExternalTool]:
        return self._tools

    def get_tool_defs(self) -> list[dict]:
        return [t.to_openai_tool_def() for t in self._tools]

    def get_function_map(self) -> dict:
        return {t.name: t.call for t in self._tools}

    def shutdown(self):
        for name, proc in list(self._servers.items()):
            _kill_proc(proc)
        self._servers.clear()
        self._tools.clear()
        logger.info("所有 MCP 服务器已关闭")


# ══════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════

def _start_stderr_drain(proc: subprocess.Popen, name: str):
    """启动 daemon 线程消费 stderr，防止管道写满死锁"""

    def _drain():
        try:
            for line in proc.stderr:
                line = line.rstrip("\n")
                if line:
                    logger.debug(f"MCP[{name}] stderr: {line}")
        except (ValueError, OSError):
            pass  # pipe closed

    t = threading.Thread(target=_drain, daemon=True)
    t.start()


def _readline_with_timeout(proc: subprocess.Popen, timeout: float = 30) -> str | None:
    """从子进程 stdout 读一行，超时返回 None (Windows 兼容)"""
    result: list[str | None] = [None]
    error: list[Exception | None] = [None]

    def _read():
        try:
            line = proc.stdout.readline()
            result[0] = line.strip() if line else None
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.warning(f"MCP: readline 超时 ({timeout}s)")
        # 线程仍在阻塞读，无法安全终止。返回 None 但进程后续需被 kill。
        return ""
    if error[0]:
        raise error[0]
    return result[0]


def _kill_proc(proc: subprocess.Popen):
    """安全终止子进程"""
    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# 全局单例
mcp_manager = MCPToolManager()
