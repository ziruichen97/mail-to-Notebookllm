# Mail-to-NotebookLM 系统设计方案

## 1. 项目概述

### 1.1 背景与动机

用户无法直接访问 NotebookLM 的 Web 界面，但仍需将视频内容（YouTube、Bilibili 等平台）的链接提交到 NotebookLM 中进行批量总结处理。本工具通过邮件作为中间通道，实现"发邮件 → 自动提取链接 → 写入 NotebookLM"的端到端自动化流程。

### 1.2 核心功能

| 功能 | 说明 |
|------|------|
| 邮件监控 | 实时监听指定邮箱的收件箱，检测新邮件 |
| 链接提取 | 从邮件正文和附件中自动识别视频平台链接 |
| 链接验证 | 校验链接格式合法性与目标页面可达性 |
| NotebookLM 写入 | 将有效链接通过 API 批量添加为 NotebookLM 数据源 |
| 权限控制 | 仅接受白名单内发件人的邮件 |
| 错误追踪 | 完整的错误日志与处理失败回执 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────┐     ┌──────────────────────────────────────────────────┐     ┌──────────────────┐
│             │     │           Mail-to-NotebookLM Service             │     │                  │
│  授权用户    │     │                                                  │     │  NotebookLM      │
│  (邮件客户端) ├────►│  ┌───────────┐  ┌───────────┐  ┌─────────────┐  ├────►│  Enterprise API   │
│             │     │  │ 邮件监控器  │─►│ 链接处理器  │─►│ NotebookLM  │  │     │  / notebooklm-py │
└─────────────┘     │  │ (Listener) │  │(Processor)│  │  写入器      │  │     │                  │
                    │  └───────────┘  └─────┬─────┘  │ (Writer)    │  │     └──────────────────┘
                    │        │              │         └─────────────┘  │
                    │        ▼              ▼                          │
                    │  ┌───────────┐  ┌───────────┐                   │
                    │  │ 权限校验器  │  │ 链接验证器  │                   │
                    │  │(AuthGuard)│  │(Validator)│                   │
                    │  └───────────┘  └───────────┘                   │
                    │        │              │                          │
                    │        ▼              ▼                          │
                    │  ┌──────────────────────────┐                   │
                    │  │    SQLite / JSON 存储     │                   │
                    │  │  (链接记录 + 处理状态)     │                   │
                    │  └──────────────────────────┘                   │
                    └──────────────────────────────────────────────────┘
```

### 2.2 组件职责

#### 2.2.1 邮件监控器 (Email Listener)

**职责**：持续监控指定邮箱账户的收件箱，实时感知新邮件到达。

**核心逻辑**：
- 使用 IMAP IDLE 协议实现推送式监控（非轮询），降低延迟与资源消耗
- 每 10 分钟自动续期 IDLE 连接，防止超时断开
- 内置自动重连机制，处理网络波动
- 获取邮件后标记为已读，避免重复处理

**处理流程**：
```
启动 → 连接 IMAP 服务器 → 进入 IDLE 监听
       ↓ (收到新邮件通知)
  获取邮件内容 → 传递给权限校验器
       ↓ (IDLE 超时)
  续期 IDLE 连接 → 继续监听
       ↓ (连接断开)
  指数退避重连 → 恢复监听
```

#### 2.2.2 权限校验器 (Auth Guard)

**职责**：验证邮件发送者是否在授权白名单中，阻止未授权访问。

**校验规则**：
1. **发件人白名单**：维护一份允许的邮箱地址列表（支持通配符，如 `*@company.com`）
2. **可选：密钥验证**：邮件主题行可包含预共享密钥，作为二次认证
3. **SPF/DKIM 头检查**：验证邮件头中的认证结果，防止发件人伪造

**配置示例**：
```yaml
auth:
  allowed_senders:
    - "user@example.com"
    - "*@trusted-domain.com"
  require_subject_key: false
  subject_key: "my-secret-key-2026"
  check_spf_dkim: true
```

#### 2.2.3 链接处理器 (Link Processor)

**职责**：从邮件正文（纯文本和 HTML）中提取视频平台链接。

**支持的平台与 URL 模式**：

| 平台 | URL 模式 |
|------|----------|
| YouTube | `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/` |
| Bilibili | `bilibili.com/video/BV`, `b23.tv/` |
| Vimeo | `vimeo.com/` |
| TED | `ted.com/talks/` |
| 通用网页 | 任何 `http(s)://` 链接（可配置是否启用） |

**提取策略**：
1. 解析邮件的 `text/plain` 和 `text/html` 两种格式
2. 使用正则表达式匹配已知平台的 URL 模式
3. 展开短链接（如 `youtu.be`、`b23.tv`）获取完整 URL
4. 去重：基于标准化后的 URL 去除重复项
5. 对每个链接附加元数据：来源邮件 ID、提取时间、平台类型

#### 2.2.4 链接验证器 (Link Validator)

**职责**：验证提取到的链接是否有效且可访问。

**验证层级**：

```
第一层：格式验证
  └─ URL 是否符合标准格式（RFC 3986）
  └─ 域名是否属于已知视频平台

第二层：可达性验证
  └─ 发送 HTTP HEAD 请求检查状态码
  └─ 超时阈值：10 秒
  └─ 重试次数：最多 2 次

第三层：内容验证（可选）
  └─ YouTube：通过 oEmbed API 确认视频存在且公开
  └─ Bilibili：通过 API 检查视频状态
```

**验证结果分类**：
- `VALID`：链接有效，可以提交
- `INVALID_FORMAT`：URL 格式错误
- `UNREACHABLE`：目标不可达（404、超时等）
- `RESTRICTED`：视频存在但受限（私有、地区限制）
- `UNSUPPORTED`：不支持的平台或内容类型

#### 2.2.5 NotebookLM 写入器 (NotebookLM Writer)

**职责**：将验证通过的链接写入 NotebookLM 作为数据源。

**集成方案（详见第 3 节技术选型）**：

提供两种互备的集成路径：

| 方案 | 适用场景 | 优势 | 限制 |
|------|---------|------|------|
| **方案 A: NotebookLM Enterprise API** | 拥有 Google Workspace Enterprise 许可 | 官方支持、稳定、有 SLA | 需要 Enterprise 许可，仅支持 YouTube（不支持 Bilibili） |
| **方案 B: notebooklm-py** | 个人用户或无 Enterprise 许可 | 免费、支持所有源类型、功能更丰富 | 非官方 API，可能随时失效 |

**写入流程**：
```
接收验证通过的链接列表
  ↓
按目标 Notebook 分组
  ↓
检查 Notebook 是否存在（不存在则创建）
  ↓
调用 batchCreate API 批量添加源
  ↓
记录每个源的 sourceId 和处理状态
  ↓
更新本地数据库中的链接状态
```

---

## 3. 技术选型

### 3.1 编程语言

**选择：Python 3.11+**

理由：
- `notebooklm-py` 是 Python 编写的，可直接 `import` 集成——选择 Go/Rust 则需要多语言混合架构
- 项目是 I/O 密集型（99% 时间在等待 IMAP/HTTP 响应），Python asyncio 与 Go/Rust 在实际延迟上无可测量差异
- `imaplib` 是标准库，`IMAPClient`、`BeautifulSoup` 等邮件/HTML 处理库成熟度领先
- NotebookLM 自动化社区几乎全部使用 Python，参考方案丰富

> 完整的 Python vs Go vs Rust 对比分析见 [docs/technical-analysis.md](technical-analysis.md#第一部分后端语言选型--python-vs-go-vs-rust)

### 3.2 核心依赖

```
# 邮件处理
IMAPClient>=3.0          # IMAP 协议高级封装，支持 IDLE
mailsuite>=1.11          # IMAP 简化客户端，内置重连机制（备选）

# NotebookLM 集成
notebooklm-py>=0.3.4     # 非官方 Python API（方案 B）
google-auth>=2.0         # Google Cloud 认证（方案 A）
httpx>=0.27              # 异步 HTTP 客户端

# 链接处理
validators>=0.22         # URL 格式验证
beautifulsoup4>=4.12     # HTML 邮件解析

# 数据存储
sqlalchemy>=2.0          # ORM（如选用 SQLite）
pydantic>=2.0            # 数据模型与配置校验

# 运维
structlog>=24.0          # 结构化日志
schedule>=1.2            # 轻量级任务调度（备选）
pyyaml>=6.0              # 配置文件解析
```

### 3.3 NotebookLM 集成方案详述

#### 方案 A：NotebookLM Enterprise API（推荐生产环境）

**前提条件**：
- Google Cloud 项目已启用 Discovery Engine API
- 拥有 NotebookLM Enterprise 许可
- 已配置 Service Account 或 OAuth 2.0 凭据

**API 调用示例**：
```
POST https://us-discoveryengine.googleapis.com/v1alpha/
     projects/{PROJECT}/locations/{LOCATION}/
     notebooks/{NOTEBOOK_ID}/sources:batchCreate

Body:
{
  "userContents": [
    {
      "videoContent": {
        "youtubeUrl": "https://youtube.com/watch?v=xxx"
      }
    },
    {
      "webContent": {
        "url": "https://bilibili.com/video/BVxxx",
        "sourceName": "Bilibili - 视频标题"
      }
    }
  ]
}
```

**注意**：Enterprise API 的 `videoContent` 仅支持 YouTube。Bilibili 等非 YouTube 平台的视频链接需使用 `webContent` 类型提交，NotebookLM 会尝试抓取页面内容。

#### 方案 B：notebooklm-py（推荐个人用户）

**认证方式**：
- 首次使用需通过浏览器登录 Google 账号
- 认证状态持久化存储在 `~/.notebooklm/storage_state.json`
- 支持通过 `NOTEBOOKLM_AUTH_JSON` 环境变量在 CI/CD 中使用

**功能优势**：
- 支持所有 NotebookLM 支持的源类型
- 可生成音频概述、视频概述、思维导图等
- 支持 CLI 和 Python API 两种使用方式
- 内置 Web/Drive 研究代理

**风险**：
- 使用未公开的 Google API，可能随时失效
- 不受 Google 官方支持

### 3.4 邮件服务兼容性

| 邮件服务商 | IMAP 支持 | IDLE 支持 | 注意事项 |
|-----------|----------|----------|---------|
| Gmail | 是 | 是 | 需启用应用专用密码或 OAuth 2.0 |
| Outlook/365 | 是 | 是 | 推荐使用 OAuth 2.0 (Microsoft Graph) |
| 自建邮件服务器 | 是 | 视配置 | 确保开启 IMAP IDLE 扩展 |
| QQ 邮箱 | 是 | 部分 | 需开启 IMAP 服务并获取授权码 |
| 163 邮箱 | 是 | 部分 | 需开启 IMAP 服务并获取授权码 |

---

## 4. 数据模型

### 4.1 核心实体

```
┌──────────────────────────────────┐
│         ProcessedEmail           │
├──────────────────────────────────┤
│ id: UUID (PK)                    │
│ message_id: str (邮件 Message-ID)│
│ sender: str                      │
│ subject: str                     │
│ received_at: datetime            │
│ processed_at: datetime           │
│ status: EmailStatus              │
│ link_count: int                  │
│ error_message: str (nullable)    │
└──────────┬───────────────────────┘
           │ 1:N
           ▼
┌──────────────────────────────────┐
│          VideoLink               │
├──────────────────────────────────┤
│ id: UUID (PK)                    │
│ email_id: UUID (FK)              │
│ url: str                         │
│ normalized_url: str              │
│ platform: Platform               │
│ title: str (nullable)            │
│ validation_status: ValidationStatus │
│ notebook_id: str (nullable)      │
│ source_id: str (nullable)        │
│ submit_status: SubmitStatus      │
│ created_at: datetime             │
│ updated_at: datetime             │
│ error_message: str (nullable)    │
└──────────────────────────────────┘

┌──────────────────────────────────┐
│         NotebookMapping          │
├──────────────────────────────────┤
│ id: UUID (PK)                    │
│ notebook_id: str                 │
│ notebook_name: str               │
│ category: str                    │
│ source_count: int                │
│ max_sources: int (默认 300)      │
│ created_at: datetime             │
└──────────────────────────────────┘
```

### 4.2 枚举定义

```python
class EmailStatus(str, Enum):
    RECEIVED = "received"
    AUTHORIZED = "authorized"
    REJECTED = "rejected"
    PROCESSED = "processed"
    FAILED = "failed"

class Platform(str, Enum):
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    VIMEO = "vimeo"
    TED = "ted"
    WEB = "web"

class ValidationStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    INVALID_FORMAT = "invalid_format"
    UNREACHABLE = "unreachable"
    RESTRICTED = "restricted"
    UNSUPPORTED = "unsupported"

class SubmitStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
```

### 4.3 存储选择

**推荐：SQLite**

理由：
- 单进程场景下性能足够
- 无需额外部署数据库服务
- 数据文件可随项目迁移
- 通过 SQLAlchemy 可在需要时轻松迁移到 PostgreSQL

**替代方案：JSON 文件存储**
- 适合极简部署场景
- 使用 `TinyDB` 或自定义 JSON 文件管理
- 不推荐在数据量 > 1000 条时使用

---

## 5. 数据流处理流程

### 5.1 主流程

```
    [用户发送邮件]
         │
         ▼
  ┌──────────────┐
  │ 1. 邮件到达  │ ◄── IMAP IDLE 推送通知
  │    收件箱    │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐     ┌──────────────┐
  │ 2. 权限校验  │────►│ 拒绝并记录日志│ (未授权发件人)
  │              │ NO  │ 发送拒绝回执  │
  └──────┬───────┘     └──────────────┘
         │ YES
         ▼
  ┌──────────────┐
  │ 3. 解析邮件  │ ◄── 解析 text/plain + text/html
  │    提取链接  │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐     ┌──────────────┐
  │ 4. 验证链接  │────►│ 标记为无效    │ (格式错误/不可达)
  │              │ ✗   │ 记录错误详情  │
  └──────┬───────┘     └──────────────┘
         │ ✓
         ▼
  ┌──────────────┐
  │ 5. 分类归组  │ ◄── 按平台/主题/日期分类
  │              │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 6. 写入      │ ◄── NotebookLM API batchCreate
  │  NotebookLM  │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 7. 发送确认  │ ◄── 回复原邮件，附处理结果摘要
  │    回执邮件  │
  └──────────────┘
```

### 5.2 分类策略

链接按以下优先级分类，决定写入哪个 Notebook：

1. **按邮件主题行**（优先级最高）：
   - 主题行格式：`[分类名] 其他内容`
   - 示例：`[机器学习] 最新的 Transformer 教程` → 写入名为"机器学习"的 Notebook
   
2. **AI 辅助分类**（可选，Phase 2）：
   - 当用户未在主题行指定标签且启用 AI 分类时，调用 LLM 分析视频标题/描述进行自动归类
   - 置信度低于阈值时自动回退到下一级策略
   - 回执邮件中明确标注分类来源（用户指定 / AI 建议 / 回退策略）
   
3. **按平台自动分类**：
   - YouTube 视频 → `YouTube Videos` Notebook
   - Bilibili 视频 → `Bilibili Videos` Notebook
   
4. **按日期聚合**（默认兜底）：
   - 无明确分类时，按 `YYYY-MM` 格式归入月度 Notebook
   - 示例：`2026-03 视频收藏`

5. **Notebook 容量管理**：
   - NotebookLM 单个 Notebook 的源数量上限为 300
   - 当 Notebook 接近上限时，自动创建新的分卷 Notebook（如 `机器学习 (2)`）

> AI 分类的详细技术分析与设计方案见 [docs/technical-analysis.md](technical-analysis.md#第二部分邮件分类策略--用户指定-vs-ai-自动归类)

### 5.3 确认回执邮件格式

处理完成后，系统自动回复发件人一封确认邮件：

```
主题: Re: [机器学习] 最新的 Transformer 教程

处理完成！以下是本次处理结果：

✅ 成功添加 (3 条)：
  1. [YouTube] https://youtube.com/watch?v=abc123
     → Notebook: 机器学习 | Source ID: src_001
  2. [YouTube] https://youtube.com/watch?v=def456
     → Notebook: 机器学习 | Source ID: src_002
  3. [Bilibili] https://bilibili.com/video/BV1xx...
     → Notebook: 机器学习 | Source ID: src_003

❌ 处理失败 (1 条)：
  4. https://example.com/broken-link
     → 原因：HTTP 404 - 页面不存在

📊 统计：
  - 总链接数：4
  - 成功：3 | 失败：1
  - 目标 Notebook：机器学习 (当前 45/300 源)
```

---

## 6. 配置管理

### 6.1 配置文件结构

使用 YAML 格式的配置文件 `config.yaml`：

```yaml
# 邮件服务器配置
email:
  imap:
    host: "imap.gmail.com"
    port: 993
    use_ssl: true
  smtp:
    host: "smtp.gmail.com"
    port: 587
    use_tls: true
  credentials:
    username: "${EMAIL_USERNAME}"      # 从环境变量读取
    password: "${EMAIL_PASSWORD}"      # 从环境变量读取
  monitoring:
    folder: "INBOX"
    idle_timeout: 600                  # IDLE 续期间隔（秒）
    reconnect_max_retries: 5
    reconnect_backoff_base: 2          # 指数退避基数（秒）

# 权限控制
auth:
  allowed_senders:
    - "myemail@gmail.com"
    - "*@my-company.com"
  require_subject_key: false
  subject_key: "${AUTH_SUBJECT_KEY}"
  check_spf_dkim: true

# 链接处理
link_processing:
  supported_platforms:
    - youtube
    - bilibili
    - vimeo
    - ted
  allow_generic_urls: false            # 是否允许非视频平台链接
  validation:
    timeout: 10                        # HTTP 请求超时（秒）
    max_retries: 2
    verify_ssl: true
  short_url_expand: true               # 是否展开短链接

# NotebookLM 配置
notebooklm:
  integration: "enterprise_api"        # "enterprise_api" 或 "notebooklm_py"

  enterprise_api:
    project_number: "${GCP_PROJECT_NUMBER}"
    location: "us"
    endpoint_location: "us"
    credentials_file: "${GOOGLE_APPLICATION_CREDENTIALS}"

  notebooklm_py:
    auth_json: "${NOTEBOOKLM_AUTH_JSON}"
    home_dir: "~/.notebooklm"

  notebook:
    default_category: "monthly"        # 默认分类策略
    max_sources_per_notebook: 280      # 留出余量
    auto_create: true                  # 自动创建不存在的 Notebook

# 分类配置
classification:
  strategy: "user_specified"           # "user_specified" | "ai_assisted" | "hybrid"
  ai:
    enabled: false                     # Phase 2 可选功能
    provider: "gemini"                 # "gemini" | "openai" | "local"
    confidence_threshold: 0.80         # AI 分类置信度阈值
    fallback: "platform"              # AI 置信度不足时的回退策略

# 存储配置
storage:
  type: "sqlite"                       # "sqlite" 或 "json"
  sqlite:
    database: "data/mail_to_notebooklm.db"
  json:
    directory: "data/json_store"

# 日志配置
logging:
  level: "INFO"
  format: "json"                       # "json" 或 "text"
  file: "logs/service.log"
  max_size_mb: 50
  backup_count: 5

# 通知配置（可选）
notifications:
  send_reply: true                     # 是否发送处理结果回执
  send_error_alert: true               # 处理失败时是否发送告警
  error_alert_email: "admin@example.com"
```

### 6.2 环境变量

所有敏感信息通过环境变量注入，不存储在配置文件中：

| 变量名 | 用途 | 必须 |
|--------|------|------|
| `EMAIL_USERNAME` | 邮箱账户用户名 | 是 |
| `EMAIL_PASSWORD` | 邮箱账户密码/应用专用密码 | 是 |
| `AUTH_SUBJECT_KEY` | 邮件主题行密钥（如启用） | 否 |
| `GCP_PROJECT_NUMBER` | Google Cloud 项目编号 | 方案 A |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP 服务账号密钥文件路径 | 方案 A |
| `NOTEBOOKLM_AUTH_JSON` | notebooklm-py 认证 JSON | 方案 B |

---

## 7. 错误处理与恢复

### 7.1 错误分类

```
┌──────────────────────────────────────────────────┐
│                   错误分类体系                    │
├────────────────┬─────────────────────────────────┤
│ 类别           │ 处理策略                         │
├────────────────┼─────────────────────────────────┤
│ 临时性错误     │                                  │
│ ├ 网络超时     │ 指数退避重试（最多 3 次）          │
│ ├ IMAP 断连    │ 自动重连（最多 5 次）              │
│ └ API 限流     │ 遵循 Retry-After 头等待后重试      │
├────────────────┼─────────────────────────────────┤
│ 永久性错误     │                                  │
│ ├ 认证失败     │ 记录日志 + 告警管理员              │
│ ├ 链接无效     │ 标记状态 + 写入错误日志            │
│ └ API 不可用   │ 切换备用方案 / 记录日志 + 告警     │
├────────────────┼─────────────────────────────────┤
│ 业务错误       │                                  │
│ ├ 未授权发件人 │ 丢弃 + 记录（不回复）              │
│ ├ 无链接邮件   │ 忽略 + 记录                       │
│ └ Notebook 满  │ 自动创建分卷 Notebook              │
└────────────────┴─────────────────────────────────┘
```

### 7.2 幂等性保证

- 每封邮件通过 `Message-ID` 头去重，防止重复处理
- 每个链接通过标准化 URL 去重，防止同一视频被多次添加
- 处理状态持久化到数据库，服务重启后可从断点恢复

### 7.3 死信队列

处理失败超过最大重试次数的链接进入"死信"状态：
- 记录完整的错误上下文（邮件 ID、链接、错误信息、尝试次数）
- 支持手动重试或批量重新处理
- 定期（每日）生成死信报告发送给管理员

---

## 8. 安全设计

### 8.1 认证与授权

```
┌──────────────────────────────────────────┐
│            多层安全防护                   │
├──────────┬───────────────────────────────┤
│ 第一层   │ 发件人白名单过滤              │
│          │ - 精确匹配或通配符模式        │
│          │ - 拒绝不在白名单中的发件人    │
├──────────┼───────────────────────────────┤
│ 第二层   │ 邮件头验证                    │
│          │ - 检查 SPF 认证结果           │
│          │ - 检查 DKIM 签名             │
│          │ - 防止邮件地址伪造            │
├──────────┼───────────────────────────────┤
│ 第三层   │ 主题密钥（可选）              │
│          │ - 邮件主题行包含预共享密钥    │
│          │ - 增加一层应用层认证          │
├──────────┼───────────────────────────────┤
│ 第四层   │ 速率限制                      │
│          │ - 每个发件人每小时最多 N 封    │
│          │ - 防止滥用和 DoS              │
└──────────┴───────────────────────────────┘
```

### 8.2 数据安全

- **传输安全**：IMAP/SMTP 强制 SSL/TLS；NotebookLM API 使用 HTTPS
- **凭据管理**：所有密钥通过环境变量注入，不硬编码
- **本地存储**：SQLite 数据库文件权限设为 `0600`（仅属主可读写）
- **日志脱敏**：日志中不记录完整邮箱地址和密钥内容

### 8.3 URL 安全

- 验证 URL scheme 仅允许 `http` 和 `https`
- 禁止处理指向私有 IP 段的链接（防 SSRF）
- 对展开后的短链接重新验证目标域名

---

## 9. 项目结构

```
mail-to-notebookllm/
├── config/
│   ├── config.yaml              # 主配置文件
│   └── config.example.yaml      # 配置文件模板
├── src/
│   ├── __init__.py
│   ├── main.py                  # 入口点
│   ├── config.py                # 配置加载与校验
│   ├── email_listener.py        # 邮件监控器
│   ├── auth_guard.py            # 权限校验器
│   ├── link_processor.py        # 链接提取与处理
│   ├── link_validator.py        # 链接验证器
│   ├── notebooklm_writer.py     # NotebookLM 写入器
│   ├── notification.py          # 回执邮件发送
│   ├── models.py                # 数据模型（Pydantic + SQLAlchemy）
│   └── storage.py               # 数据库操作
├── tests/
│   ├── __init__.py
│   ├── test_auth_guard.py
│   ├── test_link_processor.py
│   ├── test_link_validator.py
│   └── test_notebooklm_writer.py
├── data/                        # 运行时数据（git ignored）
├── logs/                        # 日志文件（git ignored）
├── docs/
│   ├── system-design.md         # 本文档
│   └── technical-analysis.md    # 技术选型与 AI 分类分析
├── .env.example                 # 环境变量模板
├── .gitignore
├── pyproject.toml               # 项目元数据与依赖
├── requirements.txt             # 依赖锁定文件
└── README.md
```

---

## 10. 部署方案

### 10.1 方案对比

| 部署方式 | 适用场景 | 成本 | 运维复杂度 |
|---------|---------|------|-----------|
| **本地运行** | 开发调试 | 无 | 低 |
| **VPS / 云主机** | 个人长期使用 | ~$5/月 | 中 |
| **Docker 容器** | 标准化部署 | 取决于宿主 | 低 |
| **Google Cloud Run** | 与 GCP 生态集成 | 按需付费 | 低 |
| **树莓派 / NAS** | 家庭内网运行 | 一次性硬件成本 | 中 |

### 10.2 推荐部署：Docker + 云主机

**Dockerfile 设计思路**：

```dockerfile
# 多阶段构建
FROM python:3.11-slim AS base
# 安装依赖，复制代码，设置非 root 用户
# 挂载 data/ 和 logs/ 为外部卷
# 入口点：python -m src.main
```

**docker-compose 设计思路**：

```yaml
services:
  mail-to-notebooklm:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config:/app/config:ro
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8080/health')"]
      interval: 60s
```

### 10.3 可选：健康检查端点

内嵌一个轻量 HTTP 服务（如 `aiohttp` 或 `FastAPI`），暴露以下端点：

| 端点 | 用途 |
|------|------|
| `GET /health` | 服务存活检查 |
| `GET /metrics` | 处理统计（已处理邮件数、成功/失败链接数等） |
| `GET /status` | 当前 IMAP 连接状态、最近处理记录 |

### 10.4 监控与告警

- **日志**：结构化 JSON 日志输出，可接入 ELK / Loki / CloudWatch
- **指标**：暴露 Prometheus 格式指标（可选）
- **告警**：
  - IMAP 连接持续失败 → 邮件/Webhook 通知管理员
  - NotebookLM API 持续失败 → 邮件/Webhook 通知管理员
  - 死信队列堆积超过阈值 → 邮件通知管理员

---

## 11. 扩展性考虑

### 11.1 未来可扩展方向

1. **多平台支持**：接入更多视频平台（抖音、西瓜视频、Coursera 等）
2. **内容预处理**：在提交 NotebookLM 前，先用 AI 生成视频摘要
3. **Telegram/Discord Bot**：除邮件外，支持通过即时通讯工具提交链接
4. **Web 管理面板**：提供简单的 Web UI 查看处理状态、管理 Notebook
5. **批量导入**：支持从 CSV/JSON 文件批量导入链接
6. **定时摘要**：定期触发 NotebookLM 生成音频概述并发送给用户

### 11.2 插件架构

预留平台适配器接口，便于扩展新的视频平台：

```python
class PlatformAdapter(Protocol):
    """视频平台适配器协议"""
    
    @property
    def platform_name(self) -> str: ...
    
    def match(self, url: str) -> bool: ...
    
    def normalize(self, url: str) -> str: ...
    
    async def validate(self, url: str) -> ValidationResult: ...
    
    def to_notebooklm_source(self, url: str) -> dict: ...
```

---

## 12. 开发路线图

### Phase 1：核心 MVP

- 邮件监控与链接提取
- YouTube 链接验证
- NotebookLM 写入（单一方案）
- 基础白名单认证
- SQLite 存储

### Phase 2：增强功能

- 多平台支持（Bilibili、Vimeo 等）
- 确认回执邮件
- AI 辅助分类（可选，Gemini API / 本地模型）
- 配置文件热加载
- Docker 部署支持

### Phase 3：运维与扩展

- 健康检查端点
- 结构化日志与监控
- 死信队列管理
- Web 管理面板（可选）

---

## 附录 A：NotebookLM API 快速参考

### 创建 Notebook

```
POST /v1alpha/projects/{PROJECT}/locations/{LOCATION}/notebooks
Body: { "displayName": "My Notebook" }
```

### 批量添加源

```
POST /v1alpha/projects/{PROJECT}/locations/{LOCATION}/notebooks/{ID}/sources:batchCreate
Body: { "userContents": [...] }
```

### 列出 Notebook

```
GET /v1alpha/projects/{PROJECT}/locations/{LOCATION}/notebooks
```

### 删除源

```
POST /v1alpha/projects/{PROJECT}/locations/{LOCATION}/notebooks/{ID}/sources:batchDelete
Body: { "names": ["SOURCE_RESOURCE_NAME"] }
```

## 附录 B：支持的 URL 正则模式

```python
URL_PATTERNS = {
    "youtube": [
        r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]{11}',
        r'https?://youtu\.be/[\w-]{11}',
        r'https?://(?:www\.)?youtube\.com/shorts/[\w-]{11}',
        r'https?://(?:www\.)?youtube\.com/live/[\w-]{11}',
    ],
    "bilibili": [
        r'https?://(?:www\.)?bilibili\.com/video/BV[\w]+',
        r'https?://b23\.tv/[\w]+',
    ],
    "vimeo": [
        r'https?://(?:www\.)?vimeo\.com/\d+',
    ],
    "ted": [
        r'https?://(?:www\.)?ted\.com/talks/[\w_]+',
    ],
}
```
