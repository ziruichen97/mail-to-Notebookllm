# Mail-to-NotebookLM

Automatically submit video links and articles to Google NotebookLM via email.

Send an email with video links → GitHub Actions processes it → Links are added to NotebookLM → You receive a confirmation reply.

## Use Case

When you can't directly access the NotebookLM web interface, simply send an email with video links:

```
To: your-bot@gmail.com
Subject: [Machine Learning] New study materials

https://www.youtube.com/watch?v=abc123
https://www.bilibili.com/video/BV1xxxx
https://youtu.be/def456
```

The system checks the inbox every 10 minutes, extracts links, validates them, submits to NotebookLM, and replies with results.

## Supported Platforms

- YouTube (`youtube.com`, `youtu.be`, `shorts`, `live`)
- Bilibili (`bilibili.com`, `b23.tv`)
- Vimeo
- TED Talks
- Generic web links (configurable)

## Key Features

- **GitHub Actions deployment** — Zero servers, zero cost, runs on free GitHub CI
- **Two processing modes** — Link extraction (default) + full-content submission (forwarded articles, newsletters)
- **Log sanitization** — All logs automatically mask email addresses and video URLs, safe for public repos
- **Smart classification** — Email subject `[tag]` maps to the corresponding Notebook
- **Access control** — Sender whitelist + optional subject key authentication
- **Dual integration paths** — Both NotebookLM Enterprise API and notebooklm-py supported
- **Processing receipts** — Auto-reply emails with success/failure details

## Quick Start

### 1. Fork This Repository

Click the **Fork** button in the top-right corner of the GitHub page.

### 2. Configure GitHub Secrets

In your forked repo, go to **Settings → Secrets and variables → Actions** and add the following secrets:

| Secret Name | Required | Description |
|-------------|----------|-------------|
| `EMAIL_USERNAME` | Yes | Monitored mailbox username (e.g., `bot@gmail.com`) |
| `EMAIL_PASSWORD` | Yes | Mailbox password or app-specific password |
| `AUTH_ALLOWED_SENDERS` | Yes | Allowed senders, comma-separated (e.g., `me@gmail.com,me@outlook.com`) |
| `EMAIL_IMAP_HOST` | No | IMAP server address (default: `imap.gmail.com`) |
| `EMAIL_IMAP_SEND_CLIENT_ID` | No | `true` (default) sends RFC 2971 IMAP ID after login; set `false` only if your server rejects the `ID` command. **Netease (163/126/188) requires client ID** — keep the default. |
| `EMAIL_SMTP_HOST` | No | SMTP server address (default: `smtp.gmail.com`) |
| `NOTEBOOKLM_AUTH_JSON` | Depends | Auth JSON for notebooklm-py |
| `NOTEBOOKLM_INTEGRATION` | No | `notebooklm_py` (default) or `enterprise_api` |
| `GCP_PROJECT_NUMBER` | Depends | Enterprise API project number |
| `GCP_CREDENTIALS_JSON` | Depends | Enterprise API service account JSON |

### 3. Configure Your Email Provider

#### Gmail
1. Enable 2-Step Verification
2. Generate an app password: [Google Account → Security → App Passwords](https://myaccount.google.com/apppasswords)
3. Ensure IMAP is enabled: Gmail Settings → Forwarding and POP/IMAP → Enable IMAP

#### Outlook / Microsoft 365
1. Set `EMAIL_IMAP_HOST` to `outlook.office365.com`
2. Set `EMAIL_SMTP_HOST` to `smtp.office365.com`

#### Other Providers
Set `EMAIL_IMAP_HOST` and `EMAIL_SMTP_HOST` to your provider's IMAP/SMTP servers.

#### Netease (163 / 126 / 188 / yeah.net)
Use the IMAP host your provider documents (e.g. `imap.163.com`, `imap.188.com`). Enable IMAP in webmail and use a **client authorization code** (授权码) as `EMAIL_PASSWORD`, not your normal web password. Netease rejects connections that omit [IMAP `ID`](https://www.ietf.org/rfc/rfc2971.html) before opening the folder (`Unsafe Login`); this project sends client identification automatically after login. If you truly need to disable it, set `EMAIL_IMAP_SEND_CLIENT_ID=false`.

### 4. Configure NotebookLM Integration

#### Option A: notebooklm-py (Recommended for personal use)

```bash
pip install notebooklm-py
pip install "notebooklm-py[browser]"
playwright install chromium

notebooklm login                    # Log in via browser
cat ~/.notebooklm/storage_state.json     # Copy this file's contents
```

Paste the contents of `storage_state.json` into the GitHub Secret `NOTEBOOKLM_AUTH_JSON`.

#### Option B: Enterprise API (Requires Google Workspace Enterprise)

1. Create a service account in the GCP Console and download the key JSON
2. Enable the Discovery Engine API
3. Paste the key JSON into `GCP_CREDENTIALS_JSON`
4. Set `GCP_PROJECT_NUMBER` and `NOTEBOOKLM_INTEGRATION=enterprise_api`

### 5. Enable Actions

Go to the **Actions** tab in your repo and enable workflows. The system will automatically check the inbox every 10 minutes.

You can also click **Run workflow** to trigger a manual test run.

## Email Format

The system supports two processing modes: **Link Extraction** (default) and **Full-Content Submission**.

### Mode 1: Link Extraction (Default)

List video links in the email body. The system extracts, validates, and submits them to NotebookLM:

```
To: bot@gmail.com
Subject: [Deep Learning] Latest Transformer tutorials

https://youtube.com/watch?v=abc
https://youtube.com/watch?v=def
https://bilibili.com/video/BVxxx
```

Use `[Category Name]` in the subject to specify a Notebook (auto-created if it doesn't exist). Without a tag, links are filed into a monthly default Notebook.

### Mode 2: Full-Content Submission

When you receive articles, newsletters, or technical write-ups from others and want to store the entire email content in NotebookLM, use full-content mode.

**Trigger methods (pick any one)**:

1. **Add an `[article]` tag in the subject** (recommended):

```
Subject: [article] A deep analysis of large language models
Subject: [article:Research] Latest Transformer paper     ← with category
Subject: [full] Curated tech blog posts
```

2. **Simply forward the email** (auto-detected via `Fwd:` prefix):

```
Subject: Fwd: Weekly AI Newsletter from TechCrunch
Subject: Fw: Technical article from a colleague
```

**How full-content mode works**:
- The complete email body is submitted as a "text source" to NotebookLM
- If the body contains video links, those links are also extracted and submitted separately
- Both go into the same Notebook for unified summarization in NotebookLM

**Reply example**:

```
Processing complete!

Mode: Full-content

Email content added as text source ✓
  → Notebook: Research

Links added (2):
  1. [youtube] https://www.youtube.com/watch?v=abc123
     → Notebook: Research
  2. [bilibili] https://www.bilibili.com/video/BV1xxxx
     → Notebook: Research

Summary:
  - Full content: submitted
  - Links found: 2
  - Valid: 2
  - Submitted: 2
  - Failed: 0
  - Target Notebook: Research
```

## Log Safety

All Actions run logs are automatically sanitized:

| Original Content | Shown in Logs |
|-----------------|---------------|
| `user@example.com` | `u***r@example.com` |
| `https://youtube.com/watch?v=abc123` | `[YouTube:***]` |
| `https://bilibili.com/video/BVxxx` | `[Bilibili:***]` |

Even with a public repo, your email address and video preferences are never exposed in logs.

## Project Structure

```
mail-to-notebookllm/
├── .github/workflows/
│   └── poll-email.yml           # GitHub Actions cron workflow
├── config/
│   └── config.example.yaml      # Configuration template
├── src/
│   ├── main.py                  # Entry point (single-run mode)
│   ├── config.py                # Configuration loading
│   ├── logger.py                # Log sanitization
│   ├── email_client.py          # IMAP fetch + SMTP reply
│   ├── auth_guard.py            # Sender whitelist
│   ├── link_processor.py        # Link extraction & deduplication
│   ├── link_validator.py        # Link validation
│   ├── notebooklm_writer.py     # NotebookLM dual-path writer
│   ├── notification.py          # Reply email builder
│   └── models.py                # Data models
├── tests/                       # Unit tests
├── docs/
│   ├── system-design.md         # System design document
│   └── technical-analysis.md    # Technical analysis
├── .env.example                 # Environment variable template
└── requirements.txt             # Python dependencies
```

## Documentation

- [System Design](docs/system-design.md) — Architecture, data models, security design
- [Technical Analysis](docs/technical-analysis.md) — Python vs Go/Rust, AI classification analysis

## License

[MIT License](LICENSE)
