# AI Agent 系统 (1号机)

基于多模型 (ModelScope / DeepSeek) 的多用户 AI Agent 系统，支持 function calling、MCP 协议、用户管理、会话记忆隔离、工具生态扩展、图片分析/编辑/生图、对话分支管理、结构化日志与全链路追踪。前后端分离架构，API 兼容原 CLI 模式。

## 功能蓝图

| 模块 | 状态 | 说明 |
|---|---|---|
| Agent 循环 | ✅ 已有 | Function calling 驱动的多轮对话，流式/非流式 |
| 天气查询工具 | ✅ 已有 | 通过 wttr.in 免费 API 查询实时天气 |
| 数学计算工具 | ✅ 已有 | 安全表达式求值 |
| 用户系统 | ✅ 已有 | 注册/登录，SHA-256 密码哈希，JWT 认证 |
| 会话管理 | ✅ 已有 | 多会话隔离，MySQL 持久化 |
| 消息持久化 | ✅ 已有 | 对话历史自动保存/加载 |
| 文件系统工具 | ✅ 已有 | 目录浏览、文件读写、搜索（安全沙箱） |
| 日期时间工具 | ✅ 已有 | 当前时间、日期计算、星期查询 |
| HTTP 请求工具 | ✅ 已有 | GET/POST 请求，支持自定义 Header |
| 系统信息工具 | ✅ 已有 | 系统状态、环境变量、进程信息 |
| 多模态图片分析 | ✅ 已有 | 上传图片 → Qwen3.5-VL 分析 → LLM 生成回复 |
| 文生图 | ✅ 已有 | Z-Image-Turbo 异步生图 + 轮询 |
| 图像编辑 | ✅ 已有 | Qwen-Image-Edit 编辑对话上文中的图片 |
| 图表生成 | ✅ 已有 | matplotlib 柱状图/折线图/饼图/散点图 |
| Excel 读写 | ✅ 已有 | openpyxl 读取和写入 Excel 文件 |
| SQL 查询 | ✅ 已有 | 安全 SQLite SELECT 查询 (沙箱) |
| 多模型支持 | ✅ 已有 | Qwen3-30B / DeepSeek V4 / Qwen3.5-VL / Z-Image-Turbo / Qwen-Image-Edit |
| DeepSeek V4 思考 | ✅ 已有 | reasoning_content 收集回传，前端可折叠显示 |
| 上下文管理 | ✅ 已有 | Token 自动计数与裁剪 |
| 流式输出 | ✅ 已有 | SSE 流式 + 打字机逐字效果 |
| 免费额度追踪 | ✅ 已有 | 文本 1800/多模态 100/生图 100 次/天 |
| 对话分支树 | ✅ 已有 | parent_id 链表树，兄弟节点导航 <N/M>，上溯构建上下文 |
| MCP 协议 | ✅ 已有 | 作为 MCP Server 暴露工具 + 连接外部 MCP Server |
| 结构化日志 | ✅ 已有 | 全链路追踪 + 审计日志 (JSON) |
| 工具队列 | ✅ 已有 | 异步工具执行，不阻塞 SSE 流 |
| Web UI | ✅ 已有 | Vue3 + Element Plus 古风水墨主题前端 |
| CLI 模式 | ✅ 已有 | 保留 `python main.py` 终端交互 |
| 用户 Key 隔离 | ✅ 已有 | 每人独立配置 API Key，DB 隔离存储 |
| 响应式布局 | ✅ 已有 | 平板/手机适配 |

## 技术栈

- **后端**: Python 3.11, FastAPI, Pydantic 2, python-jose (JWT)
- **前端**: Vue 3, TypeScript, Element Plus, Pinia, Vue Router, marked + DOMPurify
- **LLM**: ModelScope API Inference (OpenAI 兼容) + DeepSeek API
- **SDK**: openai (Python), mcp (MCP 协议)
- **数据**: MySQL 8.0 (pymysql + DBUtils 连接池), matplotlib (图表), openpyxl (Excel)
- **构建**: Vite

## 快速开始

### 1. 安装依赖

```bash
conda activate agent_web
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，关键配置项（API Key 可留空，用户可在 Web UI 中独立配置）：

```env
# ====== 全局 API Key (可选) ======
# 留空则用户在 Web UI → 设置 → API Key 中配置自己的 Key
MODELSCOPE_API_KEY=
DEEPSEEK_API_KEY=

# ====== 以下必填 ======
JWT_SECRET=change-me-in-production  # 生产环境务必更换
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=agent_db
```

> **API Key 隔离**: 每个用户可在前端设置页配置自己的 API Key，存储到 MySQL，互不可见，与 `.env` 全局 Key 完全隔离。优先使用用户 Key，未配置时回退到 `.env`。

### 3. 初始化数据库

```sql
CREATE DATABASE IF NOT EXISTS agent_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

程序启动时会自动建表和扩展列（安全迁移，幂等）。

### 4. 启动服务

```bash
# 后端 (端口 9090)
python -m uvicorn backend.main:app --host 0.0.0.0 --port 9090

# 前端 (端口 4000，代理 /api → 9090)
cd frontend
npm run dev
```

浏览器打开 `http://localhost:4000`

### CLI 模式

```bash
python main.py
```

## 项目架构

```
pythonProject1/
├── main.py                     # CLI 入口
├── agent.py                    # CLI Agent 循环
├── auth.py                     # CLI 用户认证
├── config.py                   # 基础配置 (MySQL, DeepSeek)
├── database.py                 # DBUtils 连接池 + 安全建表
├── models/                     # 数据模型层 (CLI/Web 共享)
│   ├── user.py                 # 用户 CRUD
│   ├── session.py              # 会话 CRUD
│   └── message.py              # 消息保存/加载 (parent_id 树形分支)
├── tools/                      # 工具生态 (21 个工具, 6 大类)
│   ├── __init__.py             # 工具注册中心 + JSON 配置加载
│   ├── weather.py, calculator.py
│   ├── file_ops.py             # 4 个文件工具
│   ├── datetime_tools.py       # 4 个日期工具
│   ├── web_request.py          # 2 个 HTTP 工具
│   ├── system.py               # 3 个系统工具
│   ├── multimodal.py           # 图片分析工具
│   ├── image_gen.py            # 文生图工具
│   ├── image_edit.py           # 图像编辑工具 (Qwen-Image-Edit)
│   ├── sql_tools.py            # SQL 查询工具 (SQLite)
│   ├── chart_tools.py          # 图表生成工具 (matplotlib)
│   └── excel_tools.py          # Excel 读写工具 (openpyxl)
├── backend/                    # Web 后端 (FastAPI)
│   ├── main.py                 # 入口: CORS, MCP 挂载, MCP Client 连接, 安全迁移
│   ├── config.py               # 配置: 模型列表加载 (JSON→ENV→硬编码), JWT, 额度
│   ├── logger.py               # 结构化日志 + 全链路追踪 (trace_id) + 审计日志 (JSON→文件)
│   ├── middleware/auth.py      # JWT 创建/验证 + 依赖注入
│   ├── routers/                # API 路由 (auth, sessions, chat, models, images)
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── services/               # 核心服务
│   │   ├── agent_service.py    # Agent 循环 (流式/非流式), 工具执行, 上下文管理
│   │   ├── model_manager.py    # 多模型注册 + OpenAI 客户端缓存工厂
│   │   ├── mcp_server.py       # MCP Server: 将我方工具暴露为 MCP 服务
│   │   ├── mcp_client.py       # MCP Client: 连接外部 MCP Server, 导入其工具
│   │   ├── tool_queue.py       # 异步工具执行队列: 慢工具非阻塞, Worker 消费
│   │   ├── usage_tracker.py    # 免费额度追踪: 按类型/用户/日统计
│   │   ├── token_counter.py    # Token 计数 + 上下文裁剪 (配对完整性保护)
│   │   └── image_gen.py        # 生图服务: 异步提交 + 轮询
│   └── utils/image_utils.py    # 图片格式检测 + base64 提取
├── configs/                    # JSON 配置文件 (热加载)
│   ├── models.json             # 5 个模型: Qwen3-30B, DeepSeek V4, Qwen3.5-VL, Z-Image, Qwen-Image-Edit
│   ├── tools.json              # 工具分类 (categories) + 工具设置 (tool_settings)
│   ├── mcp_servers.json        # 外部 MCP Server 列表 (filesystem, sqlite, fetch)
│   └── system_prompt.txt       # 默认系统提示词
├── tests/                      # 测试 (pytest)
│   ├── conftest.py             # fixtures
│   ├── test_token_counter.py, test_usage_tracker.py, test_tools_basic.py
│   ├── test_tool_queue.py, test_api_auth.py, test_eval_metrics.py
│   └── eval/                   # LLM 评测管线 (config, dataset, metrics, judge, reporter, runner)
├── frontend/                   # Vue 3 前端
│   └── src/
│       ├── views/              # LoginView, RegisterView, ChatView
│       ├── stores/             # Pinia (auth, session, chat, mcp)
│       ├── api/                # Axios, SSE fetch, JWT 拦截器
│       ├── components/         # ChatInput, ModelSelector, UsageBar, SettingsDialog, McpSelector
│       ├── composables/        # useTypewriter, useImageUpload
│       └── router/index.ts     # 路由 + 登录守卫
├── logs/                       # 审计日志文件 (audit.log, 10MB 轮转)
├── uploads/                    # 用户上传图片 + 图表输出
├── requirements.txt
├── .env.example
├── README.md / DEV.md / PLAN.md
```

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
| parent_id | VARCHAR(36) NULL | 树形分支父节点 ID |
| role | ENUM | system/user/assistant/tool |
| content | MEDIUMTEXT | 消息内容 |
| tool_calls | JSON | 工具调用详情 |
| reasoning_content | TEXT NULL | DeepSeek V4 思考链 |
| created_at | TIMESTAMP | 创建时间 |

### usage_logs
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT AUTO_INCREMENT PK | 自增 |
| user_id | VARCHAR(36) | 用户 |
| api_type | ENUM | text/multimodal/image_gen |
| model_id | VARCHAR(200) | 模型 |
| tokens_used | INT | Token 消耗 |
| created_at | TIMESTAMP | UTC+8 重置基准 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 → JWT |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/sessions` | 会话列表 |
| POST | `/api/sessions` | 创建会话 |
| GET | `/api/sessions/{id}` | 会话详情+消息 |
| PATCH | `/api/sessions/{id}` | 更新会话 |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| POST | `/api/chat/completions` | 聊天 (SSE stream) |
| GET | `/api/models` | 模型列表 |
| GET | `/api/tools` | 工具列表 |
| GET | `/api/usage` | 今日用量 |
| POST | `/api/images/generations` | 提交生图 |
| GET | `/api/images/generations/{task_id}` | 查询生图状态 |
| GET | `/api/keys` | 用户 API Key (脱敏) |
| PUT | `/api/keys/{provider}` | 保存 API Key |
| DELETE | `/api/keys/{provider}` | 删除 API Key |
| GET | `/api/mcp/servers` | MCP 服务器状态 |
| GET | `/api/health` | 健康检查 |

## 工具扩展指南

1. 在 `tools/` 下创建 `my_tool.py`，定义函数 + `tool_def`
2. 在 `tools/__init__.py` 注册 `function_map["my_function"] = my_function` 并 `tools.append(my_tool_def)`
3. 编辑 `configs/tools.json` 的 `categories` 字典，将工具归入对应分类
4. 可选：编辑 `configs/tools.json` 的 `tool_settings` 添加工具默认参数

## 安全注意事项

- 不要将 `.env` 提交到版本控制
- API Key 仅存储在 `.env` 中
- 密码使用 SHA-256 哈希存储
- 文件系统工具限制在用户目录范围内，禁止目录穿越
- 环境变量读取使用白名单机制
- JWT Secret 生产环境务必更换
