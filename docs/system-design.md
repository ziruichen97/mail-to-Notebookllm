# Mail-to-NotebookLM System Design

## 1. Project Overview

### 1.1 Background and Motivation

Users cannot access the NotebookLM web UI directly but still need to submit video links (YouTube, Bilibili, and similar platforms) to NotebookLM for batch summarization. This tool uses email as an intermediary channel to implement an end-to-end automated flow: **send email → extract links automatically → write to NotebookLM**.

### 1.2 Core Features

| Feature | Description |
|---------|-------------|
| Email monitoring | Listen to the configured mailbox inbox in near real time and detect new messages |
| Link extraction | Automatically identify video-platform links from message body and attachments |
| Link validation | Check link format validity and target page reachability |
| NotebookLM write | Add valid links as NotebookLM data sources in bulk via API |
| Access control | Accept mail only from senders on an allowlist |
| Error tracking | Full error logs and failure receipts for failed processing |

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────────────┐     ┌──────────────────┐
│             │     │           Mail-to-NotebookLM Service             │     │                  │
│ Authorized  │     │                                                  │     │  NotebookLM      │
│ user (mail  ├────►│  ┌───────────┐  ┌───────────┐  ┌─────────────┐  ├────►│  Enterprise API   │
│ client)     │     │  │   Email   │─►│    Link   │─►│  NotebookLM │  │     │  / notebooklm-py │
│             │     │  │ Listener  │  │ Processor │  │   Writer    │  │     │                  │
└─────────────┘     │  └───────────┘  └─────┬─────┘  └─────────────┘  │     └──────────────────┘
                    │        │              │                          │
                    │        ▼              ▼                          │
                    │  ┌───────────┐  ┌───────────┐                   │
                    │  │ Auth      │  │   Link    │                   │
                    │  │ Guard     │  │ Validator │                   │
                    │  └───────────┘  └───────────┘                   │
                    │        │              │                          │
                    │        ▼              ▼                          │
                    │  ┌──────────────────────────┐                   │
                    │  │   SQLite / JSON store    │                   │
                    │  │ (link records + status)  │                   │
                    │  └──────────────────────────┘                   │
                    └──────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

#### 2.2.1 Email Listener

**Responsibility**: Periodically check the configured mailbox inbox and fetch new messages.

**Core logic**:
- GitHub Actions Cron triggers IMAP polling every 10 minutes
- Each run fetches all UNSEEN (unread) messages
- After processing, messages are marked SEEN; native IMAP state avoids duplicate handling
- Single-run mode—exit after processing; no long-lived daemon required

**Processing flow**:
```
GitHub Actions Cron trigger
  → Connect to IMAP server
  → Fetch all UNSEEN messages
  → Process each (auth check → link extraction → validation → submit)
  → Mark as SEEN
  → Send receipt
  → Exit
```

#### 2.2.2 Auth Guard

**Responsibility**: Verify the sender is on the authorized allowlist and block unauthorized access.

**Validation rules**:
1. **Sender allowlist**: Maintain a list of permitted addresses (wildcards supported, e.g. `*@company.com`)
2. **Optional: secret in subject**: A pre-shared key in the subject line for secondary authentication
3. **SPF/DKIM header checks**: Validate authentication results in headers to reduce sender spoofing

**Configuration example**:
```yaml
auth:
  allowed_senders:
    - "user@example.com"
    - "*@trusted-domain.com"
  require_subject_key: false
  subject_key: "my-secret-key-2026"
  check_spf_dkim: true
```

#### 2.2.3 Link Processor

**Responsibility**: Extract video-platform links from the message body (plain text and HTML).

**Supported platforms and URL patterns**:

| Platform | URL patterns |
|----------|--------------|
| YouTube | `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/` |
| Bilibili | `bilibili.com/video/BV`, `b23.tv/` |
| Vimeo | `vimeo.com/` |
| TED | `ted.com/talks/` |
| Generic web | Any `http(s)://` link (enable/disable via config) |

**Extraction strategy**:
1. Parse both `text/plain` and `text/html` parts
2. Match known platform URL patterns with regular expressions
3. Expand short links (e.g. `youtu.be`, `b23.tv`) to full URLs
4. Deduplicate using normalized URLs
5. Attach metadata per link: source message ID, extraction time, platform type

#### 2.2.4 Link Validator

**Responsibility**: Verify extracted links are valid and reachable.

**Validation layers**:

```
Layer 1: Format validation
  └─ URL conforms to standard format (RFC 3986)
  └─ Domain belongs to a known video platform

Layer 2: Reachability validation
  └─ HTTP HEAD request and status code check
  └─ Timeout threshold: 10 seconds
  └─ Retries: up to 2

Layer 3: Content validation (optional)
  └─ YouTube: oEmbed API to confirm video exists and is public
  └─ Bilibili: API check for video status
```

**Validation result categories**:
- `VALID`: Link is valid and can be submitted
- `INVALID_FORMAT`: Malformed URL
- `UNREACHABLE`: Target not reachable (404, timeout, etc.)
- `RESTRICTED`: Video exists but restricted (private, region-locked)
- `UNSUPPORTED`: Unsupported platform or content type

#### 2.2.5 NotebookLM Writer

**Responsibility**: Write validated links into NotebookLM as data sources.

**Integration options (see Section 3 for technology choices)**:

Two mutually backup integration paths:

| Option | Use case | Pros | Cons |
|--------|----------|------|------|
| **Option A: NotebookLM Enterprise API** | Google Workspace Enterprise license | Official, stable, SLA | Requires Enterprise license; YouTube-only for `videoContent` (not Bilibili) |
| **Option B: notebooklm-py** | Individuals or no Enterprise license | Free, broader source types, richer features | Unofficial API; may break without notice |

**Write flow**:
```
Receive list of validated links
  ↓
Group by target Notebook
  ↓
Ensure Notebook exists (create if missing)
  ↓
Call batchCreate API to add sources in bulk
  ↓
Record each source’s sourceId and processing state
  ↓
Update link status in local database
```

---

## 3. Technology Stack

### 3.1 Programming Language

**Choice: Python 3.11+**

Rationale:
- `notebooklm-py` is Python; direct `import` integration—Go/Rust would imply a polyglot setup
- Workload is I/O-bound (~99% time waiting on IMAP/HTTP); Python asyncio shows no meaningful latency gap vs Go/Rust here
- `imaplib` is in the stdlib; `IMAPClient`, `BeautifulSoup`, and similar mail/HTML stacks are mature
- NotebookLM automation community is largely Python, with ample reference material

> For the full Python vs Go vs Rust comparison, see [docs/technical-analysis.md](technical-analysis.md).

### 3.2 Core Dependencies

```
# Email
IMAPClient>=3.0          # Higher-level IMAP; IDLE support
mailsuite>=1.11          # Simpler IMAP client with reconnect (alternative)

# NotebookLM
notebooklm-py>=0.3.4     # Unofficial Python API (Option B)
google-auth>=2.0         # Google Cloud auth (Option A)
httpx>=0.27              # Async HTTP client

# Links
validators>=0.22         # URL format validation
beautifulsoup4>=4.12     # HTML message parsing

# Storage
sqlalchemy>=2.0          # ORM (if using SQLite)
pydantic>=2.0            # Models and config validation

# Operations
structlog>=24.0          # Structured logging
schedule>=1.2            # Lightweight scheduling (alternative)
pyyaml>=6.0              # Config file parsing
```

### 3.3 NotebookLM Integration Details

#### Option A: NotebookLM Enterprise API (recommended for production)

**Prerequisites**:
- Discovery Engine API enabled on the Google Cloud project
- NotebookLM Enterprise entitlement
- Service Account or OAuth 2.0 credentials configured

**Example API call**:
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
        "sourceName": "Bilibili - Video title"
      }
    }
  ]
}
```

**Note**: Enterprise API `videoContent` supports YouTube only. Non-YouTube video URLs (e.g. Bilibili) should use `webContent`; NotebookLM will try to fetch page content.

#### Option B: notebooklm-py (recommended for individuals)

**Authentication**:
- First use requires browser login to a Google account
- Auth state persisted in `~/.notebooklm/storage_state.json`
- `NOTEBOOKLM_AUTH_JSON` env var supported for CI/CD

**Strengths**:
- Supports all source types NotebookLM supports
- Can generate audio overviews, video overviews, mind maps, etc.
- CLI and Python API
- Built-in Web/Drive research agents

**Risks**:
- Uses undocumented Google internals; may break anytime
- Not officially supported by Google

### 3.4 Email Provider Compatibility

| Provider | IMAP | IDLE | Notes |
|----------|------|------|-------|
| Gmail | Yes | Yes | App password or OAuth 2.0 required |
| Outlook/365 | Yes | Yes | OAuth 2.0 (Microsoft Graph) recommended |
| Self-hosted | Yes | Depends on config | Ensure IMAP IDLE extension enabled |
| QQ Mail | Yes | Partial | Enable IMAP and use authorization code |
| 163 Mail | Yes | Partial | Enable IMAP and use authorization code |

---

## 4. Data Model

### 4.1 Core Entities

```
┌──────────────────────────────────┐
│         ProcessedEmail           │
├──────────────────────────────────┤
│ id: UUID (PK)                    │
│ message_id: str (Message-ID)     │
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
│ max_sources: int (default 300)   │
│ created_at: datetime             │
└──────────────────────────────────┘
```

### 4.2 Enum Definitions

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

### 4.3 Storage Choice

**Recommended: SQLite**

Rationale:
- Sufficient performance for single-process use
- No separate database server
- Data file travels with the project
- SQLAlchemy eases migration to PostgreSQL if needed

**Alternative: JSON files**
- Minimal deployments
- `TinyDB` or custom JSON layout
- Not recommended beyond ~1000 records

---

## 5. Data Flow

### 5.1 Main Pipeline

```
    [User sends email]
         │
         ▼
  ┌──────────────┐
  │ 1. Message   │ ◄── GitHub Actions Cron triggers IMAP poll
  │    arrives   │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐     ┌──────────────┐
  │ 2. Auth      │────►│ Reject + log │ (unauthorized sender)
  │    check     │ NO  │ Send reject  │
  └──────┬───────┘     └──────────────┘
         │ YES
         ▼
  ┌──────────────┐
  │ 3. Parse &   │ ◄── Parse text/plain + text/html
  │    extract   │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐     ┌──────────────┐
  │ 4. Validate  │────►│ Mark invalid │ (bad format / unreachable)
  │    links     │ ✗   │ Log details  │
  └──────┬───────┘     └──────────────┘
         │ ✓
         ▼
  ┌──────────────┐
  │ 5. Classify  │ ◄── By platform / topic / date
  │    & group   │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 6. Write to  │ ◄── NotebookLM API batchCreate
  │  NotebookLM  │
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 7. Send      │ ◄── Reply with processing summary
  │    receipt   │
  └──────────────┘
```

### 5.2 Classification Strategy

Links are classified in the following priority order to choose the target Notebook:

1. **Subject line** (highest priority):
   - Format: `[Category name] other text`
   - Example: `[Machine Learning] Latest Transformer tutorial` → Notebook named "Machine Learning"

2. **AI-assisted classification** (optional, Phase 2):
   - When the user does not specify a tag in the subject and AI classification is enabled, call an LLM on title/description to auto-assign category
   - If confidence is below threshold, fall back to the next strategy
   - Receipt email states classification source (user / AI suggestion / fallback)

3. **Platform-based routing**:
   - YouTube → `YouTube Videos` Notebook
   - Bilibili → `Bilibili Videos` Notebook

4. **Monthly aggregation** (default fallback):
   - When no explicit category, use `YYYY-MM` monthly Notebook
   - Example: `2026-03 Video collection`

5. **Notebook capacity**:
   - NotebookLM caps sources per Notebook at 300
   - When near the limit, auto-create a sequel Notebook (e.g. `Machine Learning (2)`)

> For AI classification design details, see [docs/technical-analysis.md](technical-analysis.md).

### 5.3 Confirmation Receipt Format

After processing, the system replies to the sender with a confirmation message:

```
Subject: Re: [Machine Learning] Latest Transformer tutorial

Processing complete. Summary:

✅ Successfully added (3):
  1. [YouTube] https://youtube.com/watch?v=abc123
     → Notebook: Machine Learning | Source ID: src_001
  2. [YouTube] https://youtube.com/watch?v=def456
     → Notebook: Machine Learning | Source ID: src_002
  3. [Bilibili] https://bilibili.com/video/BV1xx...
     → Notebook: Machine Learning | Source ID: src_003

❌ Failed (1):
  4. https://example.com/broken-link
     → Reason: HTTP 404 - page not found

📊 Stats:
  - Total links: 4
  - Success: 3 | Failed: 1
  - Target Notebook: Machine Learning (currently 45/300 sources)
```

---

## 6. Configuration

### 6.1 Configuration File Layout

YAML configuration in `config.yaml`:

```yaml
# Mail server
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
    username: "${EMAIL_USERNAME}"      # from environment
    password: "${EMAIL_PASSWORD}"      # from environment
  monitoring:
    folder: "INBOX"
    idle_timeout: 600                  # IDLE keepalive interval (seconds)
    reconnect_max_retries: 5
    reconnect_backoff_base: 2          # exponential backoff base (seconds)

# Access control
auth:
  allowed_senders:
    - "myemail@gmail.com"
    - "*@my-company.com"
  require_subject_key: false
  subject_key: "${AUTH_SUBJECT_KEY}"
  check_spf_dkim: true

# Link processing
link_processing:
  supported_platforms:
    - youtube
    - bilibili
    - vimeo
    - ted
  allow_generic_urls: false            # allow non-video generic URLs
  validation:
    timeout: 10                        # HTTP timeout (seconds)
    max_retries: 2
    verify_ssl: true
  short_url_expand: true               # expand short URLs

# NotebookLM
notebooklm:
  integration: "enterprise_api"        # "enterprise_api" or "notebooklm_py"

  enterprise_api:
    project_number: "${GCP_PROJECT_NUMBER}"
    location: "us"
    endpoint_location: "us"
    credentials_file: "${GOOGLE_APPLICATION_CREDENTIALS}"

  notebooklm_py:
    auth_json: "${NOTEBOOKLM_AUTH_JSON}"
    home_dir: "~/.notebooklm"

  notebook:
    default_category: "monthly"        # default classification strategy
    max_sources_per_notebook: 280      # headroom below hard cap
    auto_create: true                  # auto-create missing Notebooks

# Classification
classification:
  strategy: "user_specified"           # "user_specified" | "ai_assisted" | "hybrid"
  ai:
    enabled: false                     # optional Phase 2
    provider: "gemini"                 # "gemini" | "openai" | "local"
    confidence_threshold: 0.80         # AI confidence threshold
    fallback: "platform"              # fallback when AI confidence is low

# Storage
storage:
  type: "sqlite"                       # "sqlite" or "json"
  sqlite:
    database: "data/mail_to_notebooklm.db"
  json:
    directory: "data/json_store"

# Logging
logging:
  level: "INFO"
  format: "json"                       # "json" or "text"
  file: "logs/service.log"
  max_size_mb: 50
  backup_count: 5

# Notifications (optional)
notifications:
  send_reply: true                     # send processing receipt
  send_error_alert: true               # alert on processing failure
  error_alert_email: "admin@example.com"
```

### 6.2 Environment Variables

Secrets are injected via environment variables, not stored in config files:

| Variable | Purpose | Required |
|----------|---------|----------|
| `EMAIL_USERNAME` | Mailbox username | Yes |
| `EMAIL_PASSWORD` | Mailbox password / app password | Yes |
| `AUTH_SUBJECT_KEY` | Subject-line secret (if enabled) | No |
| `GCP_PROJECT_NUMBER` | Google Cloud project number | Option A |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account key | Option A |
| `NOTEBOOKLM_AUTH_JSON` | notebooklm-py auth JSON | Option B |

---

## 7. Error Handling and Recovery

### 7.1 Error Taxonomy

```
┌──────────────────────────────────────────────────┐
│              Error taxonomy                      │
├────────────────┬─────────────────────────────────┤
│ Category       │ Handling                         │
├────────────────┼─────────────────────────────────┤
│ Transient      │                                  │
│ ├ Network T/O  │ Exponential backoff (max 3)      │
│ ├ IMAP drop    │ Auto-reconnect (max 5)           │
│ └ API throttle │ Honor Retry-After, then retry    │
├────────────────┼─────────────────────────────────┤
│ Permanent      │                                  │
│ ├ Auth failure │ Log + alert admins               │
│ ├ Bad link     │ Set state + error log            │
│ └ API down     │ Failover path / log + alert      │
├────────────────┼─────────────────────────────────┤
│ Business       │                                  │
│ ├ Unauthorized │ Drop + log (no reply)            │
│ ├ No links     │ Ignore + log                     │
│ └ Notebook full│ Auto-create sequel Notebook      │
└────────────────┴─────────────────────────────────┘
```

### 7.2 Idempotency

- Deduplicate by `Message-ID` header to avoid reprocessing the same mail
- Deduplicate links by normalized URL to avoid duplicate adds
- Persist processing state so runs can resume after restart

### 7.3 Dead Letter Queue

Links that fail after max retries enter a dead-letter state:
- Store full context (message ID, URL, error, attempt count)
- Support manual retry or batch reprocessing
- Daily dead-letter report to admins

---

## 8. Security Design

### 8.1 Authentication and Authorization

```
┌──────────────────────────────────────────┐
│        Layered security controls         │
├──────────┬───────────────────────────────┤
│ Layer 1  │ Sender allowlist              │
│          │ - Exact or wildcard match     │
│          │ - Reject non-allowlisted      │
├──────────┼───────────────────────────────┤
│ Layer 2  │ Header validation             │
│          │ - SPF result                  │
│          │ - DKIM signature              │
│          │ - Reduce address spoofing     │
├──────────┼───────────────────────────────┤
│ Layer 3  │ Subject secret (optional)     │
│          │ - Pre-shared key in subject   │
│          │ - Extra app-layer auth        │
├──────────┼───────────────────────────────┤
│ Layer 4  │ Rate limiting                 │
│          │ - Max N messages/hour/sender  │
│          │ - Abuse / DoS mitigation      │
└──────────┴───────────────────────────────┘
```

### 8.2 Data Security

- **In transit**: IMAP/SMTP over SSL/TLS; NotebookLM API over HTTPS
- **Secrets**: Keys via environment variables only; no hardcoding
- **Local storage**: SQLite file mode `0600` (owner read/write only)
- **Log redaction**: Do not log full addresses or secret values

### 8.3 URL Safety

- Allow only `http` and `https` schemes
- Block private-IP targets (SSRF mitigation)
- Re-validate destination host after short-link expansion

---

## 9. Project Layout

```
mail-to-notebooklm/
├── .github/
│   └── workflows/
│       └── poll-email.yml       # GitHub Actions scheduled workflow
├── config/
│   └── config.example.yaml      # Config template
├── src/
│   ├── __init__.py
│   ├── main.py                  # Entry (single-run mode)
│   ├── config.py                # Load & validate config
│   ├── logger.py                # Log redaction
│   ├── email_client.py          # IMAP fetch + SMTP reply
│   ├── auth_guard.py            # Auth guard
│   ├── link_processor.py        # Link extraction & handling
│   ├── link_validator.py        # Link validation
│   ├── notebooklm_writer.py     # NotebookLM writer
│   ├── notification.py          # Receipt email builder
│   └── models.py                # Data models
├── tests/
│   ├── __init__.py
│   ├── test_auth_guard.py
│   ├── test_link_processor.py
│   └── test_logger.py
├── docs/
│   ├── system-design.md         # This document
│   └── technical-analysis.md    # Stack & AI classification analysis
├── .env.example                 # Environment template
├── .gitignore
├── requirements.txt             # Python dependencies
└── README.md
```

---

## 10. Deployment

### 10.1 Option Comparison

| Deployment | Use case | Cost | Ops effort |
|------------|----------|------|------------|
| **GitHub Actions (recommended)** | Long-term personal use | Free | Very low |
| **Oracle Cloud free VPS** | Near-real-time processing | Free | Low |
| **VPS / cloud VM** | High mail volume | ~$5/mo | Medium |
| **Cloudflare Email Workers** | Own domain | Free | Low |
| **Local** | Dev/debug | None | Low |

### 10.2 Recommended: GitHub Actions

Use GitHub Actions Cron to poll the inbox every 10 minutes.

**Pattern**:
```
Every 10 min → GitHub Actions starts → IMAP connect → fetch unread
  → process links → submit to NotebookLM → send receipt → mark read → exit
```

**Benefits**:
- Free for public repos (no minute cap concern for this pattern)
- No server to operate
- Secrets in GitHub Secrets
- Log redaction for public repos
- Built-in run history and failure signals

**Workflow** (`.github/workflows/poll-email.yml`):
- Triggers: `schedule (cron: '*/10 * * * *')` + manual
- Runner: `ubuntu-latest`, Python 3.11
- State: IMAP SEEN for dedupe; no external DB required for basic mode

**Privacy**:
- GitHub masks registered Secret values in logs
- Additional redaction for addresses and URLs in logs
- Prefer aggregates in logs over raw link dumps

### 10.3 Alternate Deployments

**Oracle Cloud Always Free VPS**: For IMAP IDLE instead of 10-minute polling, use an Always Free ARM instance (4 vCPU / 24 GB) in an APAC region with a long-running Python process.

**Cloudflare Email Workers**: With your own domain, Email Routing can push events to a Worker for event-driven, low-latency handling (requires a TypeScript rewrite).

### 10.4 Monitoring and Alerts

- **Logs**: GitHub Actions logs retained ~90 days
- **Failures**: Workflow failure notifications via GitHub Actions settings
- **Manual**: Inspect each run in the Actions UI

---

## 11. Extensibility

### 11.1 Future Directions

1. **More platforms**: Douyin, Xigua, Coursera, etc.
2. **Preprocessing**: AI-generated summaries before NotebookLM ingest
3. **Telegram/Discord bots**: Submit links outside email
4. **Web admin**: Simple UI for status and Notebook management
5. **Bulk import**: CSV/JSON link imports
6. **Scheduled digests**: Trigger NotebookLM audio overviews on a schedule

### 11.2 Plugin-Oriented Adapters

Reserve a platform adapter protocol for new video sites:

```python
class PlatformAdapter(Protocol):
    """Video platform adapter protocol."""
    
    @property
    def platform_name(self) -> str: ...
    
    def match(self, url: str) -> bool: ...
    
    def normalize(self, url: str) -> str: ...
    
    async def validate(self, url: str) -> ValidationResult: ...
    
    def to_notebooklm_source(self, url: str) -> dict: ...
```

---

## 12. Development Roadmap

### Phase 1: Core MVP

- Email monitoring and link extraction
- YouTube link validation
- NotebookLM write (single integration path)
- Basic allowlist auth
- SQLite storage

### Phase 2: Enhancements

- Multi-platform (Bilibili, Vimeo, …)
- Confirmation receipts
- Optional AI-assisted classification (Gemini API / local models)
- Config hot reload
- Docker deployment

### Phase 3: Operations and Scale

- Health check endpoint
- Structured logging and monitoring
- Dead-letter management
- Optional web admin UI

---

## Appendix A: NotebookLM API Quick Reference

### Create Notebook

```
POST /v1alpha/projects/{PROJECT}/locations/{LOCATION}/notebooks
Body: { "displayName": "My Notebook" }
```

### Batch add sources

```
POST /v1alpha/projects/{PROJECT}/locations/{LOCATION}/notebooks/{ID}/sources:batchCreate
Body: { "userContents": [...] }
```

### List Notebooks

```
GET /v1alpha/projects/{PROJECT}/locations/{LOCATION}/notebooks
```

### Delete sources

```
POST /v1alpha/projects/{PROJECT}/locations/{LOCATION}/notebooks/{ID}/sources:batchDelete
Body: { "names": ["SOURCE_RESOURCE_NAME"] }
```

## Appendix B: Supported URL Regex Patterns

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
