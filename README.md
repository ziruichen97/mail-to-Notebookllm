# Mail-to-NotebookLM

通过邮件自动将视频链接提交到 Google NotebookLM。

发一封邮件，附上视频链接 → GitHub Actions 自动处理 → 链接写入 NotebookLM → 收到确认回执。

## 使用场景

当你无法直接访问 NotebookLM Web 界面时，只需发送一封包含视频链接的邮件：

```
收件人: your-bot@gmail.com
主题: [机器学习] 新的学习资料

https://www.youtube.com/watch?v=abc123
https://www.bilibili.com/video/BV1xxxx
https://youtu.be/def456
```

系统每 10 分钟自动检查收件箱，提取链接，验证有效性，提交到 NotebookLM，然后回复你处理结果。

## 支持的平台

- YouTube（`youtube.com`、`youtu.be`、`shorts`、`live`）
- Bilibili（`bilibili.com`、`b23.tv`）
- Vimeo
- TED Talks
- 通用网页链接（可配置）

## 核心特性

- **GitHub Actions 部署** — 零服务器、零成本，利用 GitHub 免费 CI 资源
- **两种处理模式** — 链接提取（默认）+ 全文提交（转发文章、Newsletter）
- **日志脱敏** — 所有日志自动遮蔽邮箱地址和视频链接，公开仓库安全可用
- **智能分类** — 邮件主题 `[标签]` 自动映射到对应 Notebook
- **安全控制** — 发件人白名单 + 可选密钥认证
- **双集成路径** — NotebookLM Enterprise API 和 notebooklm-py 均支持
- **处理回执** — 自动回复邮件，附成功/失败明细

## 快速开始

### 1. Fork 本仓库

点击 GitHub 页面右上角的 Fork 按钮。

### 2. 配置 GitHub Secrets

在你 fork 的仓库中，进入 **Settings → Secrets and variables → Actions**，添加以下 Secrets：

| Secret 名称 | 必填 | 说明 |
|-------------|------|------|
| `EMAIL_USERNAME` | 是 | 监控邮箱的用户名（如 `bot@gmail.com`） |
| `EMAIL_PASSWORD` | 是 | 邮箱密码或应用专用密码 |
| `AUTH_ALLOWED_SENDERS` | 是 | 允许的发件人，逗号分隔（如 `me@qq.com,me@163.com`） |
| `EMAIL_IMAP_HOST` | 否 | IMAP 服务器地址（默认 `imap.gmail.com`） |
| `EMAIL_SMTP_HOST` | 否 | SMTP 服务器地址（默认 `smtp.gmail.com`） |
| `NOTEBOOKLM_AUTH_JSON` | 视方案 | notebooklm-py 的认证 JSON |
| `NOTEBOOKLM_INTEGRATION` | 否 | `notebooklm_py`（默认）或 `enterprise_api` |
| `GCP_PROJECT_NUMBER` | 视方案 | Enterprise API 项目编号 |
| `GCP_CREDENTIALS_JSON` | 视方案 | Enterprise API 服务账号 JSON |

### 3. 配置邮箱

#### Gmail
1. 启用两步验证
2. 生成应用专用密码：[Google 账号 → 安全 → 应用专用密码](https://myaccount.google.com/apppasswords)
3. 确保 IMAP 已启用：Gmail 设置 → 转发和 POP/IMAP → 启用 IMAP

#### QQ 邮箱
1. 设置 → 账户 → 开启 IMAP 服务 → 获取授权码
2. `EMAIL_IMAP_HOST` 设为 `imap.qq.com`，`EMAIL_SMTP_HOST` 设为 `smtp.qq.com`

#### 163 邮箱
1. 设置 → POP3/SMTP/IMAP → 开启 IMAP → 获取授权码
2. `EMAIL_IMAP_HOST` 设为 `imap.163.com`，`EMAIL_SMTP_HOST` 设为 `smtp.163.com`

### 4. 配置 NotebookLM 集成

#### 方案 A：notebooklm-py（个人用户推荐）

```bash
pip install notebooklm-py
notebooklm auth login          # 浏览器登录 Google 账号
cat ~/.notebooklm/storage_state.json   # 复制此文件内容
```

将 `storage_state.json` 的内容粘贴到 GitHub Secret `NOTEBOOKLM_AUTH_JSON` 中。

#### 方案 B：Enterprise API（需要 Google Workspace Enterprise）

1. 在 GCP 控制台创建服务账号并下载密钥 JSON
2. 启用 Discovery Engine API
3. 将密钥 JSON 内容粘贴到 `GCP_CREDENTIALS_JSON`
4. 设置 `GCP_PROJECT_NUMBER` 和 `NOTEBOOKLM_INTEGRATION=enterprise_api`

### 5. 启用 Actions

进入仓库的 **Actions** 页面，启用 workflows。系统将自动每 10 分钟检查一次收件箱。

也可以点击 **Run workflow** 手动触发一次测试。

## 邮件格式

系统支持两种处理模式：**链接提取**（默认）和**全文提交**。

### 模式一：链接提取（默认）

在正文中列出视频链接，系统会提取、验证后提交到 NotebookLM：

```
收件人: bot@gmail.com
主题: [深度学习] 最新的 Transformer 教程

https://youtube.com/watch?v=abc
https://youtube.com/watch?v=def
https://bilibili.com/video/BVxxx
```

主题行用 `[分类名]` 指定 Notebook（不存在则自动创建）。不写标签时按月归入默认 Notebook。

### 模式二：全文提交

当你收到别人发来的文章、Newsletter、技术分享等，想把整篇邮件内容存入 NotebookLM 时，使用全文模式。

**触发方式（任选其一）**：

1. **在主题行加 `[文章]` 标签**（推荐）：

```
主题: [文章] 一篇关于大模型的深度分析
主题: [文章:机器学习] 最新的 Transformer 论文    ← 同时指定分类
主题: [全文] 技术博客精选
```

2. **直接转发邮件**（系统自动识别 `Fwd:` / `转发:` 前缀）：

```
主题: Fwd: Weekly AI Newsletter from TechCrunch
主题: 转发: 同事分享的技术文章
```

**全文模式的处理逻辑**：
- 邮件的完整正文会作为"文本源"提交到 NotebookLM
- 如果正文中包含视频链接，这些链接也会被单独提取并提交
- 两者会进入同一个 Notebook，便于在 NotebookLM 中一起总结

**回执示例**：

```
处理完成！

模式: 全文提交

邮件全文已添加为文本源 ✓
  → Notebook: 机器学习

成功添加链接 (2 条)：
  1. [youtube] https://www.youtube.com/watch?v=abc123
     → Notebook: 机器学习
  2. [bilibili] https://www.bilibili.com/video/BV1xxxx
     → Notebook: 机器学习

统计：
  - 全文提交: 成功
  - 链接数: 2
  - 有效: 2
  - 成功提交: 2
  - 失败: 0
  - 目标 Notebook: 机器学习
```

## 日志安全

所有 Actions 运行日志都经过自动脱敏处理：

| 原始内容 | 日志中显示为 |
|---------|------------|
| `user@example.com` | `u***r@example.com` |
| `https://youtube.com/watch?v=abc123` | `[YouTube:***]` |
| `https://bilibili.com/video/BVxxx` | `[Bilibili:***]` |

即使仓库公开，你的邮箱地址和视频偏好也不会暴露在日志中。

## 项目结构

```
mail-to-notebookllm/
├── .github/workflows/
│   └── poll-email.yml           # GitHub Actions 定时工作流
├── config/
│   └── config.example.yaml      # 配置文件模板
├── src/
│   ├── main.py                  # 入口点（单次运行）
│   ├── config.py                # 配置加载
│   ├── logger.py                # 日志脱敏
│   ├── email_client.py          # IMAP 收取 + SMTP 回复
│   ├── auth_guard.py            # 发件人白名单
│   ├── link_processor.py        # 链接提取与去重
│   ├── link_validator.py        # 链接验证
│   ├── notebooklm_writer.py     # NotebookLM 双路径写入
│   ├── notification.py          # 回执邮件构建
│   └── models.py                # 数据模型
├── tests/                       # 单元测试
├── docs/
│   ├── system-design.md         # 系统设计方案
│   └── technical-analysis.md    # 技术选型分析
├── .env.example                 # 环境变量模板
└── requirements.txt             # Python 依赖
```

## 文档

- [系统设计方案](docs/system-design.md) — 架构、数据模型、安全设计
- [技术选型分析](docs/technical-analysis.md) — Python vs Go/Rust、AI 分类分析

## 许可证

[MIT License](LICENSE)
