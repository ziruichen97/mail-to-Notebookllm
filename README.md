# Mail-to-NotebookLM

通过邮件自动将视频链接提交到 Google NotebookLM，实现"发邮件 → 自动提取链接 → 写入 NotebookLM"的端到端自动化。

## 使用场景

当你无法直接访问 NotebookLM Web 界面时，只需发送一封包含视频链接的邮件，系统便会自动：

1. 监控指定邮箱收件箱
2. 识别邮件中的视频链接（YouTube、Bilibili 等）
3. 验证链接有效性
4. 将有效链接批量添加到 NotebookLM 中

## 支持的平台

- YouTube（`youtube.com`、`youtu.be`）
- Bilibili（`bilibili.com`、`b23.tv`）
- Vimeo
- TED Talks
- 通用网页链接（可配置）

## 核心特性

- **实时监控**：基于 IMAP IDLE 的推送式邮件监听
- **智能分类**：按邮件主题 / 平台 / 日期自动归入不同 Notebook
- **安全控制**：发件人白名单 + SPF/DKIM 校验 + 可选密钥认证
- **双集成路径**：支持 NotebookLM Enterprise API 和 notebooklm-py
- **容错机制**：自动重试、死信队列、处理结果回执邮件

## 文档

- [系统设计方案](docs/system-design.md) — 架构、数据模型、部署方案、开发路线图
- [技术选型分析](docs/technical-analysis.md) — Python vs Go/Rust 对比、AI 分类 vs 用户指定分类分析

## 快速开始

> 项目尚处于设计阶段，代码实现即将到来。

### 前置条件

- Python 3.11+
- 一个支持 IMAP 的邮箱账户（Gmail、Outlook 等）
- NotebookLM Enterprise API 凭据 **或** notebooklm-py 认证配置

### 配置

1. 复制配置模板：`cp config/config.example.yaml config/config.yaml`
2. 设置环境变量（参见 `.env.example`）
3. 配置授权发件人白名单

## 项目结构

```
mail-to-notebookllm/
├── config/           # 配置文件
├── src/              # 源代码
│   ├── main.py       # 入口点
│   ├── email_listener.py
│   ├── auth_guard.py
│   ├── link_processor.py
│   ├── link_validator.py
│   ├── notebooklm_writer.py
│   └── ...
├── tests/            # 测试
├── docs/             # 文档
│   ├── system-design.md
│   └── technical-analysis.md
└── README.md
```

## 许可证

[MIT License](LICENSE)
