# AI Agent 系统 (1号机) — 开发文档

## 项目概述

多用户 AI Agent 系统，前后端分离架构。支持多模型 (ModelScope Qwen3 / DeepSeek V4)、Function Calling 工具生态（21 个内置工具 + 6 大类 + MCP 外部工具扩展）、多模态图片分析/编辑、异步文生图、对话分支树管理、结构化日志与全链路追踪、异步工具执行队列。保留 CLI 终端模式向后兼容。

---

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| **后端框架** | FastAPI 0.110+ | 异步 HTTP，SSE 流式 |
| **认证** | python-jose JWT | HS256，24h 过期 |
| **数据模型** | Pydantic 2 | 请求/响应校验 |
| **LLM SDK** | openai >= 1.0 | OpenAI 兼容协议 |
| **数据库** | MySQL 8.0 + pymysql + DBUtils | PooledDB 连接池 (max=20), utf8mb4 |
| **Token 计数** | tiktoken | cl100k_base 编码 |
| **MCP 协议** | mcp >= 1.27 | FastMCP (服务端) + JSON-RPC stdio (客户端) |
| **图表生成** | matplotlib | 非交互 Agg 后端，输出 PNG |
| **Excel 读写** | openpyxl | 读写 .xlsx 文件 |
| **前端框架** | Vue 3.4 + TypeScript | Composition API |
| **UI 库** | Element Plus 2.7 | 古风水墨主题 |
| **状态管理** | Pinia 2 | auth / session / chat / mcp 四个 store |
| **路由** | Vue Router 4 | 登录守卫 |
| **Markdown** | marked + DOMPurify | XSS 安全渲染 |
| **构建** | Vite 5 | HMR，/api 代理 |
| **Python 环境** | Anaconda Python 3.11 | conda env: agent_web |

---

## 项目结构

```
pythonProject1/
├── main.py                     # CLI 入口 (保留兼容)
├── agent.py                    # CLI Agent 循环
├── auth.py                     # CLI 用户认证
├── config.py                   # 基础配置 (MySQL, DeepSeek)
├── database.py                 # DBUtils PooledDB 连接池 + 幂等建表
│
├── models/                     # 数据模型层 (CLI/Web 共享)
│   ├── __init__.py
│   ├── user.py                 # 用户 CRUD (SHA-256 密码哈希)
│   ├── session.py              # 会话 CRUD
│   └── message.py              # 消息持久化: save/load + build_context + parent_id 树结构
│
├── tools/                      # 工具生态 (21 个, 6 大类)
│   ├── __init__.py             # 工具注册中心: function_map + tools + 配置加载
│   ├── weather.py              # get_weather: wttr.in 免费天气 API
│   ├── calculator.py           # calculate: 安全表达式 eval (仅算术/数学函数)
│   ├── file_ops.py             # 4 工具: list_directory, read_file, write_file, search_files
│   ├── datetime_tools.py       # 4 工具: get_current_time, calculate_date, days_between, weekday
│   ├── web_request.py          # 2 工具: http_get, http_post
│   ├── system.py               # 3 工具: get_system_info, get_env_var, get_process_info
│   ├── multimodal.py           # analyze_image: 图片预处理 → Qwen3.5-VL API
│   ├── image_gen.py            # generate_image: Z-Image-Turbo 异步生图 (60s 超时)
│   ├── image_edit.py           # edit_image: Qwen-Image-Edit-2511 图像编辑 (异步+轮询)
│   ├── sql_tools.py            # sql_query: SQLite 安全 SELECT 查询 (禁止写操作)
│   ├── chart_tools.py          # generate_chart: matplotlib 图表 (bar/line/pie/scatter)
│   └── excel_tools.py          # read_excel + write_excel: openpyxl 读写 Excel
│
├── backend/                    # Web 后端
│   ├── main.py                 # FastAPI 入口: CORS, trace 中间件, MCP 挂载/连接, 安全迁移,
│   │                           #   /api/health, /api/usage, /api/tools, /api/mcp/servers, 全局异常处理
│   ├── config.py               # 配置: 模型列表加载 (JSON → ENV → 硬编码), JWT, 额度限制
│   ├── logger.py               # 结构化日志 + 全链路追踪 (ContextVar trace_id) + 审计日志 (JSON→文件轮转)
│   ├── middleware/
│   │   └── auth.py             # JWT 创建/验证, get_current_user 依赖注入
│   ├── routers/
│   │   ├── auth.py             # POST /register, /login, GET /me (含审计日志)
│   │   ├── sessions.py         # CRUD /sessions + 消息历史
│   │   ├── chat.py             # POST /completions (SSE stream + non-stream)
│   │   ├── models.py           # GET /models 模型列表
│   │   └── images.py           # POST /generations + GET /generations/{task_id}
│   ├── schemas/
│   │   ├── auth.py             # RegisterRequest, LoginRequest, TokenResponse
│   │   ├── chat.py             # ChatRequest (含 parent_id, mcp_servers)
│   │   ├── session.py          # SessionCreate, SessionUpdate, SessionResponse
│   │   └── model.py            # ModelInfo, ModelListResponse
│   ├── services/
│   │   ├── agent_service.py    # 核心: Agent 循环 (Tool Calling) + 流式/非流式
│   │   │                       #       工具重试 + 错误降级 + 额度超限降级建议
│   │   │                       #       图片缓存恢复 + parent_id 树形上下文
│   │   │                       #       生图/编辑结果自动回存图片缓存
│   │   ├── model_manager.py    # 多模型注册 + OpenAI 客户端缓存工厂 (按 provider+url+key 缓存)
│   │   ├── mcp_server.py       # MCP Server: FastMCP 注册 21 个工具 → FastAPI 挂载 /mcp
│   │   ├── mcp_client.py       # MCP Client: stdio 连接外部 MCP Server, JSON-RPC 协议
│   │   │                       #       导入外部工具 → 合并到 Agent tool list
│   │   ├── tool_queue.py       # 异步工具队列: asyncio.Queue + Worker (to_thread 执行)
│   │   │                       #       慢工具标记 exec_mode=async → 不阻塞 SSE 流
│   │   ├── usage_tracker.py    # 免费额度追踪: 按 user_id + api_type + 日期统计
│   │   │                       #       text(1800) / multimodal(100) / image_gen(100)
│   │   ├── token_counter.py    # Token 计数 + 上下文裁剪 (tool_calls/tool_result 配对保护)
│   │   └── image_gen.py        # 生图服务: 异步提交 + 轮询 (魔搭 API)
│   └── utils/
│       └── image_utils.py      # 图片检测 (detect_images) + base64 解码 (decode_base64_image)
│
├── configs/                    # JSON 配置文件 (热加载，失败时回退硬编码)
│   ├── models.json             # 5 个模型: Qwen3-30B, DeepSeek V4, Qwen3.5-VL, Z-Image, Qwen-Image-Edit
│   ├── tools.json              # 工具分类 (categories) + 工具设置 (tool_settings: 超时/大小限制等)
│   ├── mcp_servers.json        # 外部 MCP Server: filesystem (npx), sqlite (uvx), fetch (uvx)
│   └── system_prompt.txt       # 默认系统提示词 (启发生成)
│
├── tests/                      # 测试 (pytest)
│   ├── conftest.py             # fixtures: sample_messages, sample_messages_with_tools
│   ├── test_token_counter.py   # Token 计数/裁剪测试
│   ├── test_usage_tracker.py   # 额度追踪测试
│   ├── test_tools_basic.py     # 工具函数单元测试
│   ├── test_tool_queue.py      # 异步队列测试
│   ├── test_api_auth.py        # API 认证测试
│   ├── test_eval_metrics.py    # 评测指标测试
│   └── eval/                   # LLM 评测管线
│       ├── config.py           # 评分权重, 延迟阈值, 回归检测阈值
│       ├── dataset.py          # 数据集加载
│       ├── metrics.py          # 评分计算
│       ├── judge.py            # LLM-as-Judge (DeepSeek V4 当裁判)
│       ├── runner.py           # 评测执行器
│       ├── reporter.py         # 报告输出
│       └── datasets/           # 评测数据集
│           ├── tool_calling.json
│           ├── safety.json
│           └── multimodal.json
│
├── frontend/                   # Vue 3 前端
│   ├── vite.config.ts          # Vite 配置: /api → localhost:9090 代理
│   ├── src/
│   │   ├── main.ts             # 入口: createApp + Element Plus + Pinia + Router
│   │   ├── App.vue             # 根组件
│   │   ├── types/index.ts      # TS 类型: User, Session, ModelInfo, SSEEvent, UsageInfo, McpServer
│   │   ├── router/index.ts     # /login, /register, /chat (auth guard)
│   │   ├── api/
│   │   │   ├── index.ts        # Axios 实例 + JWT 拦截器
│   │   │   ├── auth.ts         # login, register, getMe
│   │   │   ├── sessions.ts     # getSessions, createSession, getSession, deleteSession, getModels, getUsage, getMcpServers
│   │   │   └── chat.ts         # sendMessage: fetch SSE stream + parent_id + mcp_servers 传参
│   │   ├── stores/
│   │   │   ├── auth.ts         # Pinia: token, user, login, register, logout
│   │   │   ├── session.ts      # Pinia: 树形分支 (activeLeafId + childrenMap + visibleMessages)
│   │   │   ├── chat.ts         # Pinia: send, regenerate, reedit, 打字机, reasoning, pendingTools
│   │   │   └── mcp.ts          # Pinia: MCP 服务器列表, 全局开关, 多选服务器, 活跃工具列表
│   │   ├── composables/
│   │   │   ├── useTypewriter.ts   # 字符缓冲 + 定时器逐字输出 (独立 composable)
│   │   │   └── useImageUpload.ts  # FileReader base64 + 剪贴板粘贴 (独立 composable)
│   │   ├── components/
│   │   │   ├── chat/ChatInput.vue      # 输入框: 文本 + 图片上传/粘贴 + 缩略图预览 + 发送/停止
│   │   │   ├── common/ModelSelector.vue # 模型下拉选择器
│   │   │   ├── common/UsageBar.vue     # 三类额度 el-progress 进度条 (>50%黄 >80%红)
│   │   │   ├── common/SettingsDialog.vue # 设置: MCP 管理 (连接状态/工具列表/开关) + 关于
│   │   │   └── common/McpSelector.vue  # 输入框旁 MCP 选择器: popover 开关+多选+标签
│   │   └── views/
│   │       ├── LoginView.vue     # 登录页 (古风印章设计)
│   │       ├── RegisterView.vue  # 注册页
│   │       └── ChatView.vue      # 聊天主界面: 侧边栏 + 消息列表 + 分支导航 + MCP + 输入区
│   └── index.html
│
├── logs/                       # 审计日志文件 (audit.log, 10MB/5文件轮转)
├── uploads/                    # 用户上传图片 + 图表输出
├── requirements.txt            # Python 依赖
├── .env / .env.example         # 环境变量
└── README.md / DEV.md / PLAN.md
```

---

## 数据模型

### users
| 字段 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(36) PK | UUID |
| username | VARCHAR(50) UNIQUE | 用户名 |
| password_hash | VARCHAR(255) | SHA-256 哈希 |
| created_at | TIMESTAMP | 创建时间 |

### sessions
| 字段 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(36) PK | UUID |
| user_id | VARCHAR(36) FK | 所属用户 |
| title | VARCHAR(200) | 会话标题 |
| model_id | VARCHAR(100) NULL | 绑定模型 |
| system_prompt | TEXT NULL | 自定义系统提示 |
| created_at / updated_at | TIMESTAMP | 时间戳 |

### messages
| 字段 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(36) PK | UUID |
| session_id | VARCHAR(36) FK | 所属会话 |
| parent_id | VARCHAR(36) NULL | **树形分支父节点 ID** |
| role | ENUM('system','user','assistant','tool') | 消息角色 |
| content | MEDIUMTEXT | 消息内容 (文本或图片 JSON 数组) |
| tool_calls | JSON NULL | Function Calling 详情 |
| reasoning_content | TEXT NULL | DeepSeek V4 思考链 |
| branch | INT DEFAULT 1 | (遗留) 分支号 |
| turn_index | INT NULL | (遗留) 对话轮次 |
| created_at | TIMESTAMP | 创建时间 |

### usage_logs
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT AUTO_INCREMENT PK | 自增 |
| user_id | VARCHAR(36) | 用户 |
| api_type | ENUM('text','multimodal','image_gen') | 调用类型 |
| model_id | VARCHAR(200) | 模型 ID |
| tokens_used | INT | Token 消耗 |
| created_at | TIMESTAMP | UTC+8 重置基准 |

---

## API 端点

### 认证
| 方法 | 路径 | 请求体 | 响应 | 认证 |
|------|------|--------|------|------|
| POST | `/api/auth/register` | `{username, password}` | 201 `{id, username}` | 无 |
| POST | `/api/auth/login` | `{username, password}` | `{access_token, token_type, user}` | 无 |
| GET | `/api/auth/me` | - | `{id, username}` | Bearer |

### 会话
| 方法 | 路径 | 请求体 | 响应 |
|------|------|--------|------|
| GET | `/api/sessions` | - | `[{id, title, ...}]` |
| POST | `/api/sessions` | `{title?, model_id?}` | 201 `{id, title, ...}` |
| GET | `/api/sessions/{id}` | - | `{id, title, messages: [...]}` |
| PATCH | `/api/sessions/{id}` | `{title?, model_id?}` | `{id, title, ...}` |
| DELETE | `/api/sessions/{id}` | - | 204 |

### 聊天 (核心)
| 方法 | 路径 | 请求体 | 响应 |
|------|------|--------|------|
| POST | `/api/chat/completions` | `{session_id, messages, model_id?, stream?, parent_id?, mcp_servers?}` | SSE stream 或 JSON |

**SSE 事件流**:
```
data: {"type":"reasoning","content":"思考..."}     # DeepSeek V4
data: {"type":"text","content":"你好"}
data: {"type":"tool_call","id":"call_xxx","function":{"name":"get_weather","arguments":"{...}"}}
data: {"type":"tool_queued","task_id":"...","tool":"generate_image","message":"..."}   # 异步工具
data: {"type":"tool_progress","task_id":"...","elapsed_seconds":3.0}                  # 进度通知
data: {"type":"tool_result","tool_call_id":"call_xxx","content":"晴朗 25°C"}
data: {"type":"done"}
data: [DONE]
```

### 模型 & 工具 & MCP
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/models` | 可用模型列表 (含类型/上下文窗口/多模态标记) |
| GET | `/api/tools` | 已注册工具列表 (需认证) |
| GET | `/api/usage` | 今日剩余额度 (需认证) |
| GET | `/api/mcp/servers` | MCP 服务器状态: SDK 可用性, 连接状态, 工具列表 (需认证) |

### 生图
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/images/generations` | `{prompt, model_id?, size?, steps?}` → `{task_id}` |
| GET | `/api/images/generations/{task_id}` | `{status, output_images?}` |

---

## 工具生态 (21 个 + MCP 扩展)

### 工具注册
`tools/__init__.py` 维护三个全局对象：
- `function_map`: `{"func_name": callable}` — 函数名到实现的映射 (22 项)
- `tools`: `[{tool_def}, ...]` — 传给 LLM 的工具描述列表
- `TOOL_CATEGORIES`: `{"类别": [工具名列表]}` — 分类管理

额外 API：
- `load_tools_config()`: 从 `configs/tools.json` 加载分类和设置，失败回退硬编码
- `load_tool_settings()`: 获取工具设置（超时、文件大小限制等）
- `register_tool()` / `remove_tool()`: 动态注册/移除工具

### 基础工具 (5个)
| 工具 | 函数 | 实现要点 |
|------|------|---------|
| calculate | `calculate(expression)` | 安全 eval：仅允许数学/数值字面量 |
| get_current_time | `get_current_time(timezone_offset=8)` | f-string 避免 strftime % 冲突 |
| calculate_date | `calculate_date(date_str, days)` | datetime + timedelta |
| days_between | `days_between(date1, date2)` | 日期差绝对值 |
| weekday | `weekday(date_str)` | 中文星期名 |

### 网络工具 (3个)
| 工具 | 函数 | 实现要点 |
|------|------|---------|
| get_weather | `get_weather(city)` | wttr.in API, `?format=3` |
| http_get | `http_get(url, headers?)` | requests.get, 10s 超时 |
| http_post | `http_post(url, body, headers?)` | requests.post, JSON body |

### 文件工具 (4个)
| 工具 | 函数 | 实现要点 |
|------|------|---------|
| list_directory | `list_directory(path)` | 文件大小格式化，防目录穿越 |
| read_file | `read_file(path)` | 5000 字上限，1MB 文件上限，防目录穿越 |
| write_file | `write_file(path, content)` | 防目录穿越 |
| search_files | `search_files(pattern)` | glob 通配符，最多 30 个结果 |

### 系统工具 (3个)
| 工具 | 函数 | 实现要点 |
|------|------|---------|
| get_system_info | `get_system_info()` | platform + os 模块 |
| get_env_var | `get_env_var(name)` | 安全白名单 (PATH/HOME/USER/TEMP...) |
| get_process_info | `get_process_info()` | psutil (可选) |

### AI 工具 (3个)
| 工具 | 函数 | 实现要点 |
|------|------|---------|
| analyze_image | `analyze_image(image_index, question?, session_id?)` | resize ≤2048px → JPEG q85 → base64 → Qwen3.5-VL API |
| generate_image | `generate_image(prompt, size?, steps?)` | Z-Image-Turbo 异步提交 → 轮询 (60s 超时) |
| edit_image | `edit_image(prompt, image_index?, steps?, guidance?)` | Qwen-Image-Edit-2511 异步提交 → 轮询 (60s 超时) |

### 数据工具 (4个) — v1.4 新增
| 工具 | 函数 | 实现要点 |
|------|------|---------|
| sql_query | `sql_query(query, db_path?)` | SQLite SELECT only，禁止 INSERT/UPDATE/DELETE/DROP，最多 50 行 |
| generate_chart | `generate_chart(chart_type, data, title?, x_label?, y_label?)` | matplotlib Agg 后端，bar/line/pie/scatter，输出 PNG |
| read_excel | `read_excel(file_path, sheet?, max_rows?)` | openpyxl read_only，最多 100 行，防目录穿越 |
| write_excel | `write_excel(data, output_file)` | JSON 二维数组 → .xlsx，保存到用户主目录 |

### 工具分类配置 (configs/tools.json)
```json
{
  "categories": {
    "基础工具": ["calculate", "get_current_time", "calculate_date", "days_between", "weekday"],
    "网络工具": ["get_weather", "http_get", "http_post"],
    "文件工具": ["list_directory", "read_file", "write_file", "search_files"],
    "系统工具": ["get_system_info", "get_env_var", "get_process_info"],
    "AI工具": ["analyze_image", "generate_image", "edit_image"],
    "数据工具": ["sql_query", "generate_chart", "read_excel", "write_excel"]
  },
  "tool_settings": {
    "file_ops": { "max_read_size": 5000 },
    "image_gen": { "timeout": 60, "default_size": "1024x1024" },
    "weather": { "api_url": "https://wttr.in/{city}?format=3" }
  }
}
```

---

## MCP 协议架构

### 服务端 (MCP Server)
- `backend/services/mcp_server.py` + FastMCP
- 启动时注册全部 21 个内置工具 → 挂载到 FastAPI `/mcp` 路径
- 外部应用 (Claude Desktop / Cursor) 可通过 MCP 协议调用我方工具
- SDK 未安装时静默降级，不影响 Web 服务

### 客户端 (MCP Client)
- `backend/services/mcp_client.py` + `configs/mcp_servers.json`
- 启动时读取配置 → 对 enabled 的 stdio 服务器发起 JSON-RPC 连接
- `initialize` → `tools/list` → 包装为 MCPExternalTool → 合并到 Agent 工具列表
- 工具名加 `mcp_<server>_` 前缀防止冲突
- 前端支持：McpSelector (开关/多选), SettingsDialog (状态监控), ChatRequest.mcp_servers 传参

### 配置 (configs/mcp_servers.json)
```json
[
  {"name": "filesystem", "transport": "stdio", "command": "npx",
   "args": ["-y", "@modelcontextprotocol/server-filesystem", "."], "enabled": true},
  {"name": "sqlite", "transport": "stdio", "command": "uvx",
   "args": ["mcp-server-sqlite", "--db-path", "data.db"], "enabled": true},
  {"name": "fetch", "transport": "stdio", "command": "uvx",
   "args": ["mcp-server-fetch"], "enabled": true}
]
```

---

## 异步工具队列 (tool_queue.py)

### 设计目的
慢工具 (生图、编辑、图片分析) 执行时间 10-60s，不能阻塞 SSE 流。通过消息队列解耦执行。

### 架构
```
Agent 循环 (异步)
  │ tool_queue.is_async_tool(func_name) → True?
  ├─ 是: await tool_queue.submit() → Worker (to_thread) 执行 → yield tool_progress → yield tool_result
  └─ 否: ToolExecutor.execute() 原地同步执行
```

### 关键实现
- 工具定义加 `"exec_mode": "async"` 标记慢工具
- `AsyncToolQueue`: asyncio.Queue + Event 通知机制
- Worker: `asyncio.to_thread()` 在线程池中执行阻塞函数
- SSE 进度通知: 每 3s 发送 `tool_progress` 事件
- 总超时: 90s (由 Agent 循环的 while 循环控制)

---

## 结构化日志 & 全链路追踪 (logger.py)

### TraceContext
- `ContextVar` 存储 `trace_id`, `user_id`, `model_id`, `start_time`, `tool_calls[]`
- 请求进入时 `ctx.start()`，每个 HTTP 响应带 `X-Trace-Id` 头
- 工具执行时 `ctx.add_tool()`，完成时计算 `ctx.latency_ms`

### 双通道输出
| 通道 | 目标 | 格式 | 说明 |
|------|------|------|------|
| 控制台 | stderr | 文本: `%(asctime)s [%(levelname)s] %(name)s: %(message)s` | 开发调试 |
| 文件 | logs/audit.log | JSON: `{"ts":"...","trace_id":"...","user":"...","event":"..."}` | 审计归档 |

### 审计事件
- `audit_chat_completion(model, tokens, latency_ms, tool_calls)`
- `audit_tool_exec(tool, success, latency_ms)`
- `audit_quota_check(api_type, remaining)`
- `audit_login(username, success)`
- `audit_register(username)`

---

## 多模型管理

### ModelManager 设计

```python
class ModelManager:
    _models: dict[str, ModelConfig]    # model_id → 配置
    _clients: dict[str, OpenAI]        # cache_key → 客户端 (按 provider+base_url+api_key 缓存)
    _default_id: str

    def get_client(model_id) -> OpenAI:     # 获取或创建客户端
    def get_config(model_id) -> ModelConfig: # 获取模型配置
    def has_model(model_id) -> bool:         # 模型是否存在
```

### 配置加载顺序: JSON 文件 → 环境变量 → 硬编码默认值

### 已注册模型 (configs/models.json)
| ID | 提供商 | 类型 | 上下文窗口 | 说明 |
|----|--------|------|-----------|------|
| Qwen/Qwen3-30B-A3B | ModelScope | text | 32K | 主力文本对话模型 |
| deepseek-v4-flash | DeepSeek | text | 64K | 独立 API Key，支持思考链 |
| Qwen/Qwen3.5-397B-A17B | ModelScope | multimodal | 128K | 图片分析模型 |
| Tongyi-MAI/Z-Image-Turbo | ModelScope | image_gen | - | 文生图模型 |
| Qwen/Qwen-Image-Edit-2511 | ModelScope | image_edit | - | 图像编辑模型 (v1.4 新增) |

---

## 树形分支系统

### 设计原理

每个消息存储 `parent_id` 指向父消息，形成单向链表。上下文通过沿链上溯构建：

```
root (parent_id=null)
└── user:"猫作文" (parent=root)
    ├── asst:"优雅的..." (parent=user)  ← 原始回复
    ├── asst:"另一种..." (parent=user)  ← regenerate (兄弟!)
    │   └── user:"你是什么" (parent=asst_2)
    │       └── asst:"通义千问..." (parent=user_2)
    └── user:"编辑后" (parent=root)     ← reedit (兄弟!)
        └── asst:"新回答..." (parent=user_3)
```

### 前端实现

```typescript
// session.ts — 核心逻辑 (~20 行)
const activeLeafId = ref<string | null>(null)  // 当前活跃叶节点

const childrenMap = computed(() => {  // parentId → 子节点列表
  const map = new Map<string, string[]>()
  for (const m of messages.value) {
    const pid = m._parentId
    if (pid) { /* add to map */ }
  }
  return map
})

const visibleMessages = computed(() => {  // 从叶到根上溯
  const chain = []
  let id = activeLeafId.value
  while (id) {
    const msg = messages.value.find(m => m.id === id)
    if (!msg) break
    chain.unshift(msg)
    id = msg._parentId ?? null
  }
  return chain
})
```

### 三种操作

| 操作 | 前端触发 | parent_id 传递 | 后端行为 |
|------|---------|---------------|---------|
| **send** | 输入框发送 | `activeLeafId` (上次助手) | 新建 user → 新建 asst (user 的子) |
| **regenerate** | 点击重新生成 | 原用户消息的 id | 复用 user，新建 asst (user 的子) |
| **reedit** | 编辑后重发 | 原用户消息的 parent | 新建 user_edit → 新建 asst (user_edit 的子) |

### 分支导航
```
用户消息上显示:  1 / 2 / 3  <2/3>
                 ↑   ↑   ↑    ↑ ↑
              分支1 分支2 分支3  活跃=2，总数=3
```

---

## DeepSeek V4 思考模式

### 数据流

```
LLM stream chunk
  ↓ delta.model_extra['reasoning_content']
agent_service 收集 → SSE {"type":"reasoning","content":"..."}
  ↓
前端 chat.ts: reasoningContent.value += event.content
  ↓
ChatView.vue: el-collapse "思考过程" 可折叠面板
```

### 关键实现细节
- `reasoning_content` 在 `model_extra` 字典中，不是直接属性
- 工具调用场景必须回传 reasoning_content
- DB `messages.reasoning_content TEXT` 列存储
- `message_to_api_format()` 加载时回传

---

## 多模态图片分析流程

```
1. 用户上传/粘贴图片 → FileReader → base64 data URI
2. 前端发送 content: [{type:"image_url", image_url:{url:"data:..."}}, {type:"text", text:"..."}]
3. 后端 agent_service: _extract_content() 分离文本+图片 → store_session_images()
4. 发送给 LLM 的 content: "[用户发送了N张图片(图片0,图片1)] + 文本"
5. LLM 调用 analyze_image(image_index=0)
6. 工具函数: 读文件/URL → resize(max 2048px) → JPEG(q85) → base64 → Qwen3.5-VL API
7. 返回文字描述 → LLM 生成最终回复
8. 图片 URL 持久化在 messages.content (JSON 数组)，重启后 _restore_session_images() 恢复缓存
```

**已知问题**:
- `_to_llm_format()` 将历史图片消息转为 `[用户附带了N张图片]`，丢失具体图片索引信息
- 多轮对话后 LLM 无法区分"第一张图"vs"第二张图"
- System prompt 写死 `image_index=0`，LLM 不会智能选择索引

**魔搭 API 图片上限** (消融实验):
- 分辨率: ≤ 2048×2048
- 格式: JPEG, quality ≥ 70
- base64 字符: ~88K (2048px 时)
- `detail:low` 和 `extra_body` 均非必须

---

## 免费额度追踪

| 类型 | 每日上限 | API 操作 |
|------|---------|---------|
| text | 1800 | 每次 /chat/completions 调用 |
| multimodal | 100 | 每次 analyze_image 工具调用 |
| image_gen | 100 | 每次 generate_image / edit_image 工具调用 |

- UTC+8 每日 00:00 重置
- `usage_logs` 表按 user_id + api_type + 日期统计
- 超限返回 429 或 SSE error + 降级建议
- 前端 `UsageBar.vue` 用 `el-progress` 显示三类额度，>50% 黄色，>80% 红色
- `usage_tracker.py` 单例模式：`check_quota()` → `log_usage()` → `get_remaining()`

---

## 开发历史与问题记录

### v1.0 — CLI 时期 (2026-04)
- 基础 Agent 循环 + 15 个工具
- MySQL 持久化: users, sessions, messages
- 用户认证 (SHA-256)

### v1.1 — Web 前端 (2026-05-04)
- FastAPI + Vue3 + Element Plus 前后端
- JWT 认证，SSE 流式聊天
- 多模态图片分析 + 文生图
- 17 个工具，多模型支持
- DeepSeek V4 reasoning 回传
- 免费额度追踪
- **中断点**: 分支系统代码已写但未测试

### v1.2 — P0/P1 完善 (2026-05-08)
- 实现 `process_non_streaming`
- 分支持久化 (branch/turn_index 写入 MySQL)
- regenerate 修复 (支持图片内容)
- 打字机逐字渲染
- DB 迁移安全化 (INFORMATION_SCHEMA)
- 删除死代码 (services/multimodal.py)
- 生图轮询 60s 超时
- DeepSeek V4 思考链前端渲染
- UsageBar 额度组件
- 响应式布局
- useTypewriter / useImageUpload composables

### v1.3 — 树形分支重构 (2026-05-09)
- 数据模型: `(turn_index, branch)` → `parent_id` 单向链表
- 后端: `build_context()`, regenerate 自动检测
- 前端: 移除 turnBranches 复杂过滤，改用 activeLeafId + 上溯链
- 兄弟节点分支导航 (getSiblings / switchToSibling)
- ChatRequest: branch/turn_index → parent_id

### v1.4 — 工具扩展 + MCP + 日志 (2026-05-10)
- **新工具** (5个): edit_image (Qwen-Image-Edit), sql_query (SQLite SELECT), generate_chart (matplotlib), read_excel, write_excel (openpyxl)
- **MCP 协议**: 服务端 FastMCP 暴露 21 个工具 + 客户端连接外部 MCP Server (filesystem/sqlite/fetch)
- **结构化日志**: TraceContext (全链路 trace_id), 控制台+审计日志 (JSON→文件轮转) 双通道
- **异步工具队列**: tool_queue.py, 慢工具解耦 (exec_mode=async), SSE 进度通知, to_thread 线程池执行
- **DBUtils 连接池**: PooledDB 替代裸 pymysql 连接, max=20, mincached=2
- **JSON 配置系统**: configs/ (models.json, tools.json, mcp_servers.json, system_prompt.txt), 热加载, 失败回退硬编码
- **前端 MCP UI**: McpSelector (开关+多选+标签), SettingsDialog (MCP 管理面板), mcp store, ChatRequest.mcp_servers 全链路
- **模型新增**: Qwen-Image-Edit-2511 (image_edit 类型)
- **评测管线**: tests/eval/ (config, dataset, metrics, judge, reporter, runner) + 3 个评测数据集
- **前端版本**: SettingsDialog 关于页显示 v1.3 (待更新)

### v1.4.1 — API Key 解耦 + MCP 修复 + 评测完善 (2026-05-11)
- **API Key 用户隔离**: user_api_keys 表 + models/api_key.py + api_keys 路由 + 前端设置页
  - 每个用户独立配置 ModelScope/DeepSeek Key，存储到 DB，互不可见
  - 优先使用用户 Key，未配置时回退 `.env` 全局 Key
  - Key 脱敏显示 (前4后4)
- **MCP 外部导入修复**: Windows `npx`→`npx.cmd`、补全 `notifications/initialized` 握手、stderr 消费防死锁、超时机制、init 响应校验
  - filesystem 成功导入 14 个工具
- **图片工具会话隔离**: analyze_image/edit_image tool_def 加 session_id，agent_service 自动注入
- **E2E 评测假阳性修复**: 辅助函数只在真正失败时返回错误消息，passed=True 时清空 error 字段
- **生图状态 PROCESSING**: 增加对魔搭 API PROCESSING 状态的支持
- **重复常量清理**: backend/config.py 删除重复的 DAILY_*_LIMIT 定义
- **前端版本号**: SettingsDialog v1.3 → v1.4

### 已修复的错误


| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | `get_current_time` 格式化字符串冲突 | `strftime("%..." % offset)`，Python `%` 和 strftime `%` 冲突 | 拆分为 f-string |
| 2 | tool_calls JSON 序列化失败 | OpenAI SDK 返回 Pydantic 对象 | `_serialize_tool_calls()` → `.model_dump()` |
| 3 | models/__init__.py 导入不存在的函数 | 导出 `get_session_messages`，实际函数是 `load_session_history` | 对齐导出 |
| 4 | Windows GBK 终端编码错误 | CMD 默认 GBK，emoji 无法输出 | `PYTHONIOENCODING=utf-8` |
| 5 | venv pip 与 Python 3.12 不兼容 | pip 21.3.1 过旧 | 重建 Anaconda Python 3.11 venv |
| 6 | WindowsApps Python 劫持 | Store 占位程序排在其他 Python 之前 | 调整 PATH 优先级 |
| 7 | `process_non_streaming` 未实现 | AttributeError | 复用 process_streaming 收集结果 |
| 8 | 分支系统 HMR 状态丢失 | turnBranches Map 在热更新下重置 | 重构为 parent_id 树结构 |
| 9 | regenerate 不支持图片消息 | 提取 text 丢失了数组 content | 传递原始 content |
| 10 | DeepSeek V4 tool_calls 不完整错误 | trim_messages 切断 tool_calls/tool_result 配对 | 配对完整性检查 |
| 11 | 生图无限阻塞 | 轮询无最大等待时间 | 60s 超时 + requests.Timeout 处理 |
| 12 | ALTER TABLE 重复执行报错 | 裸 try/except 吞掉所有异常 | INFORMATION_SCHEMA 幂等检查 |
| 13 | 分支过滤逻辑复杂且边界情况多 | (turn_index, branch) 二维过滤 | parent_id 树链表 + 上溯 |

### 已知问题 (v1.4.1)

| # | 优先级 | 问题 | 根因 | 状态 |
|---|--------|------|------|------|
| 1 | P0 | 多轮对话后 LLM "看不到"上下文图片 | `_to_llm_format()` 将图片数组转为 `[用户附带了N张图片]` | 待修 |
| 2 | P0 | LLM 机械使用 image_index=0 | system_prompt.txt 写死 `image_index=0` | 待修 |
| 3 | P1 | Token 裁剪窗口过小 | `MAX_CONTEXT_TOKENS=8000`，实际仅 6000 | 待修 |
| 4 | P1 | `_session_images` 纯内存存储 | 服务重启后丢失 | 待修 |
| 5 | ✅ | SettingsDialog 版本号 → v1.4 | 已修 | v1.4.1 |
| 6 | P2 | 前端消息临时 ID (`_tmp_`) | 刷新后丢失 | 待修 |

---

## 待改进项

### 功能增强
| 优先级 | 内容 | 说明 |
|--------|------|------|
| P0 | 图片上下文传递修复 | `_to_llm_format()` 保留图片 URL/索引信息，system prompt 改为智能选择 image_index |
| P0 | Token 限制按模型调整 | 根据 model_config.context_window 动态计算阈值，而非硬编码 6000 |
| P1 | 消息 ID 与后端同步 | 前端用临时 ID (`_tmp_`)，刷新后丢失。应等后端返回真实 ID 后替换 |
| P1 | 前端主动刷新分支状态 | selectSession 后扫描 childrenMap 重建分支索引 |
| P2 | MessageBubble 组件提取 | ChatView.vue 仍 380 行，消息渲染可提取为独立组件 |
| P2 | 消息编辑历史 | 编辑后旧内容不可见，可加"查看原消息" |
| P2 | 分支可视化树 | 侧边栏或弹窗展示完整对话树 |

### 测试覆盖
| 内容 | 说明 |
|------|------|
| 后端 API 自动化测试 | pytest + httpx 覆盖所有端点 |
| 前端 E2E 测试 | Playwright: 注册 → 登录 → 聊天 → 分支切换 → 生图 |
| CLI 模式回归测试 | `python main.py` 全流程 + 工具调用 |
| 并发测试 | 多用户同时 SSE 流式聊天 |
| 超限测试 | 模拟达到每日额度限制 |

---

## 启动命令

```bash
# 后端 (需先 conda activate agent_web)
cd D:\AI\pythonProject1
python -m uvicorn backend.main:app --host 0.0.0.0 --port 9090

# 前端
cd D:\AI\pythonProject1\frontend
npm run dev

# CLI 模式
python main.py
```

浏览器: `http://localhost:4000`
