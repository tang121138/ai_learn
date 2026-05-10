# Vue + FastAPI 前端 & 多模型混合管道 实施方案

## Context

为现有的 AI Agent CLI 项目（D:\AI\pythonProject1）添加 Web 前端和更多模型能力：
1. Vue 3 + FastAPI 前后端分离架构
2. 支持多模型列表（魔搭 API Inference 为主）
3. 混合多模态管道：图片 → 魔搭/百炼多模态模型分析 → 强 LLM 生成最终回复
4. 生图能力：Z-Image + Qwen-Image 异步生图
5. 根据魔搭免费额度（2000次/天）设置调用上限，避免付费

## 关键调研结论

### 魔搭 API 体系
- **API Inference 文本对话**: `https://api-inference.modelscope.cn/v1` (OpenAI 兼容)，用 `ms-` token 认证
- **API Inference 生图**: `https://api-inference.modelscope.cn/v1/images/generations` (异步模式，需轮询 task 状态)
- **多模态 VL 模型**: Qwen2.5-VL 系列在魔搭上可供下载，但免费 API Inference 是否支持需实测。如果不支持，需走百炼 DashScope API (`https://dashscope.aliyuncs.com/compatible-mode/v1`)
- **免费额度**: 每日 2000 次（所有模型合计），单模型上限 50~500 次/天，UTC+8 00:00 重置

### 可用模型
| 类型 | 模型 ID | 用途 |
|------|---------|------|
| 文本 | `Qwen/Qwen3-30B-A3B` | 主力文本 LLM |
| 文本 | `deepseek-ai/DeepSeek-R1` | 深度推理 |
| 多模态 | `Qwen/Qwen3.5-397B-A17B` | 图像分析（默认多模态模型） |
| 文本(备选) | `deepseek-ai/DeepSeek-R1` | 深度推理 |
| 生图 | `Tongyi-MAI/Z-Image-Turbo` | 默认文生图（高效6B参数） |
| 生图(备选) | `Qwen/Qwen-Image` | 备选文生图 |

---

## 一、项目结构

```
D:\AI\pythonProject1\
├── main.py                      # 保留: CLI 入口
├── agent.py                     # 保留: CLI Agent 循环
├── config.py                    # 保留: 基础配置
├── database.py                  # 保留: MySQL 连接
├── auth.py                      # 保留: CLI 认证
├── models/                      # 保留: user, session, message
├── tools/                       # 保留: 15个工具
│
├── backend/                     # 新建: FastAPI 后端
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用入口, CORS, 生命周期
│   ├── config.py                # 扩展配置: JWT, 模型列表, 限额
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth.py              # JWT 创建+验证依赖
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py              # /api/auth/register, /login, /me
│   │   ├── sessions.py          # /api/sessions CRUD
│   │   ├── chat.py              # /api/chat/completions (SSE)
│   │   ├── models.py            # /api/models 模型列表
│   │   └── images.py            # /api/images/generations 生图(异步)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py              # Pydantic 请求/响应模型
│   │   ├── session.py
│   │   ├── chat.py
│   │   └── model.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent_service.py     # 核心: Agent 循环(流式+非流式)
│   │   ├── model_manager.py     # 多模型注册/客户端工厂
│   │   ├── multimodal.py        # 混合多模态管道
│   │   ├── image_gen.py         # 生图服务(异步提交+轮询)
│   │   ├── usage_tracker.py     # 免费额度追踪+限额
│   │   └── token_counter.py     # Token 计数+裁剪(从 agent.py 提取)
│   └── utils/
│       ├── __init__.py
│       └── image_utils.py       # Base64 解码, 图片验证
│
├── frontend/                    # 新建: Vue 3 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── api/
│   │   │   ├── index.ts         # Axios 实例+拦截器
│   │   │   ├── auth.ts
│   │   │   ├── sessions.ts
│   │   │   ├── chat.ts          # SSE 流式请求
│   │   │   └── models.ts
│   │   ├── stores/
│   │   │   ├── auth.ts          # Pinia: token, user
│   │   │   ├── session.ts       # Pinia: sessions, messages
│   │   │   └── chat.ts          # Pinia: streaming, tools, model
│   │   ├── router/
│   │   │   └── index.ts         # /login, /register, /chat
│   │   ├── composables/
│   │   │   ├── useSSE.ts        # SSE 流处理
│   │   │   └── useImageUpload.ts
│   │   ├── views/
│   │   │   ├── LoginView.vue
│   │   │   ├── RegisterView.vue
│   │   │   └── ChatView.vue
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── AppLayout.vue
│   │   │   │   └── Sidebar.vue
│   │   │   ├── chat/
│   │   │   │   ├── MessageList.vue
│   │   │   │   ├── MessageBubble.vue
│   │   │   │   ├── ChatInput.vue
│   │   │   │   ├── StreamingContent.vue
│   │   │   │   └── ToolCallIndicator.vue
│   │   │   ├── auth/
│   │   │   │   ├── LoginForm.vue
│   │   │   │   └── RegisterForm.vue
│   │   │   └── common/
│   │   │       ├── ModelSelector.vue
│   │   │       └── UsageBar.vue    # 免费额度使用情况
│   │   └── types/
│   │       └── index.ts
│   └── public/
│       └── favicon.ico
│
└── .env                         # 扩展新配置项
```

---

## 二、API 端点设计

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 `{username, password}` → 201 |
| POST | `/api/auth/login` | 登录 → `{access_token, token_type, user}` |
| GET | `/api/auth/me` | 当前用户信息 (需 Bearer Token) |

### 会话
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions` | 用户会话列表 |
| POST | `/api/sessions` | 创建会话 `{title?, model_id?}` |
| GET | `/api/sessions/{id}` | 会话详情+消息历史 |
| PATCH | `/api/sessions/{id}` | 更新标题/模型 |
| DELETE | `/api/sessions/{id}` | 删除会话 |

### 聊天 (核心)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/completions` | 发送消息，`stream:true` 返回 SSE |

**SSE 事件流格式**:
```
data: {"type":"text","content":"你好"}
data: {"type":"tool_call","id":"call_xxx","function":{"name":"get_weather","arguments":"{...}"}}
data: {"type":"tool_result","tool_call_id":"call_xxx","content":"晴朗 25°C"}
data: {"type":"multimodal_analysis","content":"图像分析: 一只橙色猫..."}   // 混合管道特有
data: {"type":"done","usage":{"total_tokens":150}}
data: [DONE]
```

### 模型 & 工具
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/models` | 可用模型列表+类型(文本/多模态/生图) |
| GET | `/api/tools` | 已注册工具列表 |
| GET | `/api/usage` | 今日 API 调用次数统计 |

### 生图 (异步)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/images/generations` | 提交生图任务 → `{task_id}` |
| GET | `/api/images/generations/{task_id}` | 查询任务状态 → `{status, output_images?}` |

---

## 三、数据库变更

`sessions` 表新增两列（向后兼容，不影响 CLI）:
```sql
ALTER TABLE sessions ADD COLUMN model_id VARCHAR(100) DEFAULT NULL;
ALTER TABLE sessions ADD COLUMN system_prompt TEXT DEFAULT NULL;
```

新增 `usage_logs` 表（追踪免费额度）:
```sql
CREATE TABLE IF NOT EXISTS usage_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    api_type ENUM('text','multimodal','image_gen') NOT NULL,
    model_id VARCHAR(200) NOT NULL,
    tokens_used INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_date (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 四、混合模型 Tool Calling 架构（改造方案）

**核心思路**：多模态分析和生图不搞硬编码管道，而是注册为**标准 Tool**，
让主 LLM 像调用 `get_weather`、`calculate` 一样自动决定何时调用。

```
用户发送 [文本 + 图片]
        │
        ▼
  后端提取图片，暂存到会话内存，文本部分只保留 "[用户发送了图片(id=0)] + 原文"
        │
        ▼
  主 LLM (Qwen3-30B) 思考 → "用户发了图片，我需要调用 analyze_image 工具"
        │
        ▼
  LLM 返回 tool_call: analyze_image(image_index=0)
        │
        ▼
  agent_service 执行工具 → 从会话缓存取出图片 → 调用 Qwen3.5-VL 多模态API
        │
        ▼
  返回分析文本给 LLM → LLM 继续思考 → 生成回复

同理生图：用户"画一只猫" → LLM 调用 generate_image(prompt="一只猫") → Z-Image API → 返回图片
```

**关键改造点**:
- 新增 `tools/multimodal.py`: `analyze_image` 工具（调用多模态模型）
- 新增 `tools/image_gen.py`: `generate_image` 工具（调用生图API）
- 注册到 `tools/__init__.py`，与现有15个工具并列
- `agent_service.py` 移除硬编码多模态管道，改为通用 Tool Calling 循环
- 图片暂存会话内存，tool 函数通过 index 读取

---

## 五、免费额度追踪 (usage_tracker.py)

```python
class UsageTracker:
    DAILY_LIMITS = {
        "text": 1800,        # 文本对话预留 1800 次
        "multimodal": 100,   # 多模态分析预留 100 次
        "image_gen": 100,    # 生图预留 100 次
    }
    # 合计 2000 次，与魔搭免费额度匹配

    def check_quota(self, user_id, api_type) -> bool:
        """检查是否还有额度"""
        today_count = self._get_today_count(user_id, api_type)
        return today_count < self.DAILY_LIMITS[api_type]

    def log_usage(self, user_id, api_type, model_id, tokens=0):
        """记录一次 API 调用"""
        ...

    def get_remaining(self, user_id) -> dict:
        """返回各类剩余次数"""
        ...
```

前端 `UsageBar.vue` 显示今日剩余额度，接近上限时警告。

---

## 六、.env 新配置项

```env
# JWT
JWT_SECRET=your-jwt-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# 魔搭 API Inference
MODELSCOPE_API_KEY=ms-ce97a9ff-81b3-48c3-bed3-a3b6b4c99784
MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1

# 模型配置
DEFAULT_MODEL=Qwen/Qwen3-30B-A3B
MULTIMODAL_MODEL=Qwen/Qwen3.5-397B-A17B
IMAGE_GEN_MODEL=Tongyi-MAI/Z-Image-Turbo

# 免费额度上限
DAILY_TEXT_LIMIT=1800
DAILY_MULTIMODAL_LIMIT=100
DAILY_IMAGE_GEN_LIMIT=100
```

---

## 七、前端技术选型

选用 **Element Plus** — 中文文档最完善 (element-plus.org/zh-CN)，Vue 3 生态最成熟，社区资源丰富。

核心依赖:
- vue 3.4, vue-router 4, pinia 2
- element-plus 2.7
- marked + dompurify (Markdown 渲染)
- highlight.js (代码高亮)
- axios (HTTP)

---

## 八、实施顺序

### 阶段 0: 环境准备（立即执行）
0. Anaconda 创建新虚拟环境 `agent_web`，Python 3.11，安装依赖

### 阶段 1: 后端基础设施（Demo v0.1 — FastAPI 启动）
1. `backend/config.py` — 扩展配置
2. `backend/main.py` — FastAPI 应用骨架
3. `backend/middleware/auth.py` — JWT 中间件
4. `backend/schemas/` — Pydantic 模型
5. `backend/services/token_counter.py` — 提取 Token 计数
6. `backend/services/model_manager.py` — 多模型管理

### 阶段 2: Demo v0.2 — API 路由 + 聊天可用（curl 可测）
7. `backend/routers/auth.py` — 注册/登录
8. `backend/routers/sessions.py` — 会话 CRUD
9. `backend/services/agent_service.py` — Agent 循环核心
10. `backend/routers/chat.py` — SSE 聊天端点
11. `backend/routers/models.py` — 模型列表
12. `backend/services/usage_tracker.py` — 额度追踪

### 阶段 3: Demo v0.3 — 多模态+生图管道联通
13. `backend/utils/image_utils.py` — 图片处理
14. `backend/services/multimodal.py` — 混合多模态管道
15. 集成到 `agent_service.py` — 自动路由
16. `backend/services/image_gen.py` + `backend/routers/images.py` — 生图 API

### 阶段 4: Demo v0.4 — 前端基础 + 聊天可用
17. Vite + Element Plus + Router + Pinia 脚手架
18. 登录/注册页面 + auth store + 路由守卫
19. 会话侧边栏 + 会话管理
20. 聊天界面: 消息列表 + 输入框 + SSE 流式显示
21. 模型选择器 + 额度显示

### 阶段 5: Demo v0.5 — 前端完善: 生图+多模态
22. 图片上传/粘贴 + 多模态消息发送
23. 生图面板 + 异步轮询 + 结果展示
24. ToolCallIndicator + 错误处理

### 阶段 6: 打磨
25. CLI 兼容性测试
26. 样式优化 + 响应式适配

---

## 九、验证方案

1. **后端单元测试**: 用 pytest 测试 auth、sessions、model_manager
2. **API 测试**: 用 httpx/curl 手动测试所有端点，确认 SSE 流正常
3. **多模态管道测试**: 上传一张图片，验证分析→注入→回复完整链路
4. **额度追踪测试**: 模拟达到限额，确认拒绝请求
5. **生图测试**: 提交生图任务，轮询直到完成
6. **前端 E2E**: 注册→登录→创建会话→文字聊天→图片消息→生图→切换模型
7. **CLI 回归**: 运行 `python main.py` 确认 CLI 模式不受影响

---

## 十、新增 Python 依赖

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
python-jose[cryptography]>=3.3.0
pydantic>=2.0.0
python-multipart>=0.0.9
Pillow>=10.0.0
httpx>=0.27.0
```

---

## 2026-05-04 进度记录 — 停止点

### 已完成

| # | 模块 | 内容 |
|---|------|------|
| 1 | 环境 | conda `agent_web` (Python 3.11) |
| 2 | 后端核心 | FastAPI app, JWT中间件, 多模型管理器, Pydantic schemas, Token裁剪 |
| 3 | API路由 | 认证/会话/聊天SSE/模型/生图/用量/工具 共12个端点 |
| 4 | 工具系统 | 17个工具含 `analyze_image` + `generate_image` |
| 5 | 多模态 | 图片预处理(resize 2048px+JPEG q85)+base64直传魔搭API |
| 6 | 消融实验 | 魔搭API图片上限: 2048x2048, JPEG>=70, base64~88K字符 |
| 7 | 额度追踪 | 按类型计次(文本1800/多模态100/生图100), MySQL持久化 |
| 8 | 前端基础 | Vite+Vue3+Element Plus, 登录/注册, 古风水墨UI |
| 9 | 聊天UI | 消息气泡, 图片缩略图, Markdown渲染, 操作按钮 |
| 10 | 多模型 | Qwen3-30B, DeepSeek-V4-Flash, Qwen3.5-VL, Z-Image-Turbo |
| 11 | DeepSeek V4 | `reasoning_content` 收集(model_extra)+回传, DB加列 |
| 12 | 图片对话修复 | 历史转纯文本, 本地URL死锁修复(直接读文件) |
| 13 | SSE流式 | `asyncio.sleep(0)`强制flush, Vite代理禁用缓冲 |

### 中断于此: 对话分支树

**已写但未测试的代码**:
- `stores/session.ts` — `turnBranches` Map, `visibleMessages` computed, `createBranch`, `switchBranch`
- `stores/chat.ts` — `regenerate(userMsgIndex)` 创建新分支
- `views/ChatView.vue` — `visibleMessages`渲染, 分支导航 `<N/M>` 按钮

**可能的bug**:
- `visibleMessages` 过滤条件
- `turnBranches` Map 在 HMR 下状态丢失
- 切换分支后新消息继承当前分支
- regenerate 时取 text 和 turnIndex 是否正确

### 待改进

| 优先级 | 内容 |
|--------|------|
| P0 | 测试分支系统, 重启前端验证 |
| P0 | 打字机效果优化(流式块太大) |
| P1 | 生图占位polling结果替换 |
| P1 | DeepSeek V4 reasoning_content 前端渲染(思维链折叠) |
| P2 | 编辑/复制功能测试 |
| P2 | 响应式布局 |
| P2 | CLI兼容测试 |

### 服务启动命令

```bash
# 后端 (需先 conda activate agent_web)
cd D:\AI\pythonProject1
python -m uvicorn backend.main:app --host 0.0.0.0 --port 9090

# 前端
cd D:\AI\pythonProject1\frontend
npm run dev
```

---

## 2026-05-08 进度记录 — 完善优化

### P0 修复

| # | 模块 | 内容 |
|---|------|------|
| 1 | 非流式端点 | `process_non_streaming()` 复用流式循环收集结果 |
| 2 | 分支持久化 | `save_message_raw` / `load_session_history_raw` 支持 branch+turn_index 列 |
| 3 | 分支传参 | `ChatRequest` + router + agent_service + api/chat.ts 全链路传递 |
| 4 | regenerate 修复 | 传原始 content (支持图片), 请求体含 branch/turn_index |
| 5 | 打字机效果 | 字符缓冲队列 + setInterval 30ms 逐字输出 |
| 6 | DB 迁移安全化 | INFORMATION_SCHEMA 查询替代裸 try/except, 幂等迁移 |

### P1 修复

| # | 模块 | 内容 |
|---|------|------|
| 7 | 思考链渲染 | SSEEvent 加 reasoning 类型, chat.ts 收集, ChatView el-collapse 可折叠显示 |
| 8 | 死代码清理 | 删除 `backend/services/multimodal.py` (零引用) |
| 9 | 生图超时 | `tools/image_gen.py` 轮询加 60s 超时 + requests.Timeout 异常处理 |

### P2 打磨

| # | 模块 | 内容 |
|---|------|------|
| 10 | UsageBar | 新建组件, 三类额度 el-progress 显示, 侧边栏底部集成 |
| 11 | 响应式 | ChatView 加 ≤1024px / ≤768px media queries |
| 12 | composables | 新建 `useTypewriter.ts` + `useImageUpload.ts` |
| 13 | 文档更新 | README/DEV/PLAN 全面更新反映当前状态 |

---

## 2026-05-09 进度记录 — 树形分支重构 (v1.3)

### 背景
(turn_index, branch) 二维坐标方案存在根本性问题：过滤逻辑复杂（跨 turn 传播、用户消息归属）、无法自然表达树形结构、深层嵌套时 switchBranch 需重置所有后续 turn。

### 方案
每个消息存储 `parent_id` 指向父消息，形成单向链表。上下文通过沿链上溯构建。每个节点只知道"回复谁"。

### 修改文件 (7个)

| # | 文件 | 变更 |
|---|------|------|
| 1 | `backend/main.py` | 添加 parent_id VARCHAR(36) NULL 列迁移 |
| 2 | `models/message.py` | save 返回 message_id + parent_id 参数；load 返回 id/parent_id；新增 build_context() 上溯函数 |
| 3 | `backend/schemas/chat.py` | ChatRequest: branch/turn_index → parent_id |
| 4 | `backend/routers/chat.py` | 传递 parent_id |
| 5 | `backend/services/agent_service.py` | parent_id 替代 branch/turn_index；自动检测 regenerate（parent 是 user msg 时不新建 user msg） |
| 6 | `frontend/src/stores/session.ts` | 重写：移除 turnBranches/turnCounter，改用 activeLeafId + childrenMap + visibleMessages 上溯链 |
| 7 | `frontend/src/stores/chat.ts` | 重写：currentParentId 替代 currentBranch/currentTurnIndex；send/regenerate/reedit 树逻辑 |
| 8 | `frontend/src/api/chat.ts` | parentId 替代 branch/turnIndex |
| 9 | `frontend/src/views/ChatView.vue` | 基于 getSiblings/switchToSibling 的分支导航 UI |

### 验证结果
- normal send: user(parent=null) → asst(parent=user) ✅
- regenerate: 两个 asst 共享同一 user 为 parent (兄弟节点) ✅
- 未新建重复 user 消息 ✅
- build_context() 沿链上溯正确 ✅
- 前端 TypeScript 编译通过 ✅

### 服务启动命令 (不变)

```bash
# 后端
cd D:\AI\pythonProject1
python -m uvicorn backend.main:app --host 0.0.0.0 --port 9090

# 前端
cd D:\AI\pythonProject1\frontend
npm run dev
```

---

## 2026-05-10 进度记录 — 工具扩展 + MCP + 日志系统 (v1.4)

### 新增工具 (5个, 21→22 注册项)

| # | 工具 | 文件 | 模型/库 | 说明 |
|---|------|------|---------|------|
| 1 | edit_image | tools/image_edit.py | Qwen-Image-Edit-2511 | 异步图像编辑, 引用对话上文图片, 60s 轮询 |
| 2 | sql_query | tools/sql_tools.py | sqlite3 | 安全 SQLite SELECT, 禁止写操作, 最多 50 行 |
| 3 | generate_chart | tools/chart_tools.py | matplotlib | 柱状图/折线图/饼图/散点图, 输出 PNG 到 uploads/ |
| 4 | read_excel | tools/excel_tools.py | openpyxl | 读取 .xlsx, read_only 模式, 最多 100 行, 防目录穿越 |
| 5 | write_excel | tools/excel_tools.py | openpyxl | JSON 二维数组 → .xlsx, 保存到用户主目录 |

### MCP 协议支持

| # | 模块 | 内容 |
|---|------|------|
| 1 | backend/services/mcp_server.py | FastMCP 注册 21 个内置工具 → 挂载 FastAPI /mcp |
| 2 | backend/services/mcp_client.py | JSON-RPC stdio 连接外部 MCP Server, tools/list 发现工具 |
| 3 | configs/mcp_servers.json | 3 个外部服务器: filesystem (npx), sqlite (uvx), fetch (uvx) |
| 4 | frontend/src/stores/mcp.ts | Pinia store: 服务器列表, 全局开关, 多选, 活跃工具计算 |
| 5 | frontend McpSelector.vue | 输入框旁 popover: 开关 + 多选 + 标签显示 |
| 6 | frontend SettingsDialog.vue | MCP 管理面板: 连接状态, 工具列表, 刷新按钮, SDK 警告 |
| 7 | backend/main.py | /api/mcp/servers 端点, 启动时加载 mcp_manager |
| 8 | ChatRequest.mcp_servers | 前端传参 → 后端 (当前未启用动态 MCP, 预留) |

### 结构化日志 & 全链路追踪

| # | 模块 | 内容 |
|---|------|------|
| 1 | backend/logger.py | TraceContext (ContextVar), setup_logging(), get_logger() |
| 2 | 全链路 trace_id | HTTP 中间件注入 → X-Trace-Id 响应头, ContextVar 跨协程传播 |
| 3 | 审计日志 | JSON 格式 → logs/audit.log, RotatingFileHandler (10MB×5) |
| 4 | 审计事件 | chat_completion, tool_exec, quota_check, login, register |
| 5 | 路由集成 | auth.py router 调用 audit_login/audit_register |
| 6 | Agent 集成 | agent_service 调用 audit_chat_completion, audit_tool_exec, audit_quota_check |

### 异步工具执行队列

| # | 模块 | 内容 |
|---|------|------|
| 1 | backend/services/tool_queue.py | AsyncToolQueue (asyncio.Queue + Event 通知) |
| 2 | Worker | asyncio.to_thread 在线程池执行阻塞函数 |
| 3 | SSE 进度 | tool_queued → tool_progress (每 3s) → tool_result |
| 4 | 慢工具标记 | tool_def.exec_mode = "async" (analyze_image, generate_image, edit_image) |
| 5 | 超时保护 | Agent 循环 90s 总超时 (当前仅 Worker 端可用) |

### 基础设施改进

| # | 模块 | 内容 |
|---|------|------|
| 1 | database.py | DBUtils PooledDB 连接池 (max=20, mincached=2, blocking=True) |
| 2 | configs/ | 新目录: models.json(5模型), tools.json(分类+设置), mcp_servers.json, system_prompt.txt |
| 3 | backend/config.py | _load_model_configs(): JSON → ENV → 硬编码 三级回退 |
| 4 | tools/__init__.py | load_tools_config(), load_tool_settings(), get_tool_categories() |
| 5 | requirements.txt | 新增: DBUtils, mcp[cli], matplotlib, openpyxl |
| 6 | 模型 | 新增 Qwen-Image-Edit-2511 (image_edit 类型) |

### 前端新增

| # | 模块 | 内容 |
|---|------|------|
| 1 | stores/mcp.ts | MCP 状态管理: servers, sdkAvailable, mcpEnabled, selectedServers, activeTools |
| 2 | McpSelector.vue | 输入框旁 popover: 全局开关 + 服务器多选 + 工具标签 |
| 3 | SettingsDialog.vue | 设置弹窗: MCP 管理 (连接状态/工具列表/刷新) + 关于 (版本号硬编码 v1.3) |
| 4 | ChatInput.vue | 增强: 图片缩略图预览, 单张删除, 粘贴多图支持 |

### 评测管线

| # | 模块 | 内容 |
|---|------|------|
| 1 | tests/eval/ | config (评分权重, 回归阈值 5%), metrics (5 维评分) |
| 2 | LLM-as-Judge | judge.py, DeepSeek V4 当裁判模型 |
| 3 | 数据集 | tool_calling.json, safety.json, multimodal.json |
| 4 | 回归检测 | runner.py + reporter.py, 分数下降 >5% 视为回归 |

### 已知问题 (v1.4 末)

| # | 优先级 | 问题 | 根因 |
|---|--------|------|------|
| 1 | P0 | 多轮对话后 LLM 无法区分历史图片 | `_to_llm_format()` 将图片数组转为 `[用户附带了N张图片]` |
| 2 | P0 | LLM 机械使用 image_index=0 | system_prompt.txt 写死参数 |
| 3 | P1 | Token 裁剪窗口 6000 vs 模型 32K-64K 上限 | MAX_CONTEXT_TOKENS=8000 硬编码 |
| 4 | P1 | SettingsDialog 版本号显示 v1.3 | 硬编码未更新 |
| 5 | P2 | 前端消息使用临时 _tmp_ ID | 未实现后端 ID 回传替换 |

### 服务启动命令 (不变)

```bash
# 后端
cd D:\AI\pythonProject1
python -m uvicorn backend.main:app --host 0.0.0.0 --port 9090

# 前端
cd D:\AI\pythonProject1\frontend
npm run dev
```
