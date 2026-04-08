# StoneFly AI Advisory Panel

A standalone web application that answers 16 pre-selected performance, sizing, and configuration questions about StoneFly Storage Appliances — and also accepts custom storage/backup/infrastructure questions — using real quote data from the StoneFly Product Configurator API and GPT-4o as the AI backend.

---

## What It Does

Load a quote number from the StoneFly Product Configurator and ask the AI questions like:

- What IOPS and throughput can I expect from this appliance?
- How fast will a single backup job run?
- What RAID configuration is best for my use case?
- How much rack space does this appliance need?
- What UPS size do I need?
- How much SSD do I need for SNSD S3?
- What deduplication savings can I expect?

The AI reads your actual appliance configuration (drive count, drive type, RAID level, network ports, cache, etc.) and gives calibrated, specific answers — not generic estimates.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Browser (frontend/index.html + app.js)                 │
│  • Dark sidebar: quote loader, config chips, Q list     │
│  • Chat area: message timeline, live streaming tokens   │
│  • Connects to backend via SSE (Server-Sent Events)     │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP POST /api/ask-stream (SSE)
┌────────────────────▼────────────────────────────────────┐
│  FastAPI Backend (app.py, port 8000)                    │
│  • Serves frontend via StaticFiles                      │
│  • Fetches quote config from Athar's Quote API          │
│  • Builds prompt with appliance config + calibration    │
│  • Streams tokens from OpenAI gpt-4o to frontend       │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴──────────────┐
         │                          │
┌────────▼──────┐        ┌──────────▼──────────┐
│  OpenAI API   │        │  StoneFly Quote API  │
│  gpt-4o       │        │  ( endpoint)         │
└───────────────┘        └─────────────────────┘
```

---

## File Structure

```
ai-advisory-panel/
│
├── app.py                        # FastAPI entry point — all API endpoints
│
├── core/
│   ├── advisory_engine.py        # Prompt builder + OpenAI API caller (sync + async streaming)
│   ├── config_model.py           # Pydantic v2 models for appliance config
│   ├── quote_import.py           # Fetches quote from API, parses flat text into structured config
│   ├── calibration.py            # Real-world QoS degradation engine (RAID penalties, load factors)
│   └── session_store.py          # In-memory singleton session state
│
├── data/
│   ├── hardware_baselines.json   # Per-drive-type IOPS/throughput baselines, SSD metadata ratios
│   └── calibration_factors.json  # RAID penalties, protocol overhead, load degradation multipliers
│
├── prompts/
│   ├── system_base.txt           # AI system prompt — identity, response format rules, scope
│   ├── q01_iops_throughput.yaml  # Question 1: IOPS & throughput
│   ├── q02_restore_rate.yaml     # Question 2: restore rate
│   ├── q03_backup_speed.yaml     # Question 3: backup speed
│   ├── q04_network_throughput.yaml
│   ├── q05_raid_recommendation.yaml
│   ├── q06_rebuild_time.yaml
│   ├── q07_power_consumption.yaml
│   ├── q08_rack_units.yaml
│   ├── q09_ups_requirements.yaml
│   ├── q10_ssd_sizing.yaml       # SNSD S3 SSD metadata tier sizing (10 GiB/TiB HDD)
│   ├── q11_storage_efficiency.yaml
│   ├── q12_dedup_index.yaml      # Dedup RAM ~5 GB/TB, index ~18 GB/TB
│   ├── q13_concurrent_jobs.yaml
│   ├── q14_cache_storage.yaml
│   ├── q15_bonding_mode.yaml
│   └── q16_backup_storage.yaml
│
├── frontend/
│   ├── index.html                # Dark sidebar + chat UI (no build step, Tailwind via CDN)
│   ├── app.js                    # Chat timeline, SSE streaming, markdown rendering, LaTeX stripping
│   └── style.css                 # Custom styles: thinking dots, avatars, tables, animations
│
├── tests/
│   ├── test_config_model.py      # 9 Pydantic model tests
│   ├── test_calibration.py       # 16 calibration engine tests
│   └── test_advisory_engine.py   # 14 engine tests (OpenAI client mocked)
│
├── requirements.txt
├── .env                          # NOT committed — see Setup below
└── .env.example                  # Template for required environment variables
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/harishstone/ai-advisory-panel.git
cd ai-advisory-panel
```

### 2. Install Python dependencies

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

### 3. Create your `.env` file

Copy `.env.example` and fill in the real values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=sk-...your-key-here...
ADVISORY_MODEL=gpt-4o
QUOTE_API_URL=https://staging.stonefly.com/api/quote_config_json.php
QUOTE_API_TOKEN=abcd....
```

> **Note:** Do NOT wrap values in quotes. Just `KEY=value` with no quotes.

### 4. Start the backend

```bash
python app.py
```

The server starts on `http://localhost:8000`.

### 5. Open the frontend

Open your browser and go to:

```
http://localhost:8000
```

The backend serves the frontend automatically. Do not open `frontend/index.html` directly from the filesystem — it must be served through the backend so API calls work.

---

## Using the App

### Load a Quote

1. Enter a quote number in the sidebar (e.g. `1775512473115`)
2. Click **Load Quote**
3. The appliance configuration chips appear below (drive count, type, RAID, cache, etc.)

### Ask a Pre-Selected Question

Click any of the 16 questions in the sidebar. The AI will answer based on your loaded quote config. Responses stream in real time like ChatGPT.

### Ask a Custom Question

Type any storage/backup/infrastructure question in the chat input box at the bottom and press **Enter** or click **Send**.

The AI handles:
- Technical questions (IOPS, throughput, sizing, power, dedup, etc.) — uses full appliance config + calibration context
- Conversational questions (who are you, what can you do, explain X) — answers naturally without generating unsolicited estimates
- Off-topic questions — politely declines

---

## API Endpoints

All endpoints are on `http://localhost:8000`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serves `frontend/index.html` |
| GET | `/health` | Health check — returns `{"status": "ok"}` |
| POST | `/api/load-quote` | Fetch quote from StoneFly API and store in session |
| GET | `/api/config` | Return the current session's appliance config |
| POST | `/api/ask-stream` | SSE stream — answer a question in real time |

### POST `/api/load-quote`

```json
{ "quote_number": "1775512473115" }
```

Returns the parsed `ApplianceConfig` object.

### POST `/api/ask-stream`

```json
{ "question_id": 1 }              // pre-selected question (1–16)
{ "question": "What RAID..." }    // custom question
```

Returns a `text/event-stream` (SSE) with events:

```
data: {"type": "start", "question": "...", "warnings": [...]}
data: {"type": "token", "text": "..."}
data: {"type": "token", "text": "..."}
data: {"type": "done"}
```

---

## How Quote Parsing Works

The StoneFly Quote API returns a flat list of product description strings, e.g.:

```
"StoneFly 12-Bay NVMe-based NAS/SAN/iSCSI Storage Appliance"
"12 x 10TB SAS HDD"
"RAID 6 Configuration"
"2 x 25GbE NIC"
```

`core/quote_import.py` uses regex patterns to extract structured fields from these strings:

- Drive count and capacity from `"12 x 10TB SAS HDD"`
- RAID level from `"RAID 6 Configuration"`
- NIC count and speed from `"2 x 25GbE NIC"`
- Cache, bay count, protocol, etc.

The parsed data is stored in a `ApplianceConfig` Pydantic model and held in the in-memory `SessionStore`.

---

## How Calibration Works

`core/calibration.py` applies real-world degradation factors to the raw hardware baselines:

- **RAID penalties**: RAID 5/6 write penalty, parity overhead on rebuild
- **Protocol overhead**: iSCSI, NFS, S3 protocol CPU overhead
- **Load factors**: typical 70% load, not 100% theoretical max
- **Veeam factors**: compression ratio effects on backup/restore speed

Calibration warnings are surfaced in the response when data is incomplete (e.g. missing drive specs).

---

## How Streaming Works

1. Frontend sends `POST /api/ask-stream` with fetch API (not EventSource — SSE over POST requires fetch)
2. Backend builds the prompt, calls `openai.AsyncOpenAI` with `stream=True`
3. FastAPI returns a `StreamingResponse` with `media_type="text/event-stream"`
4. As OpenAI yields token chunks, backend wraps each in `data: {...}\n\n` and flushes
5. Frontend reads from `response.body.getReader()`, parses SSE lines, accumulates full text
6. On every token: `innerHTML = formatResponse(fullText)` — markdown renders live as tokens arrive

`formatResponse()` handles:
- LaTeX stripping (`\( \times \)` → `×`)
- Markdown bold/italic/inline code
- Section headings (ALL CAPS lines → styled headers)
- Bullet lists
- Markdown tables → HTML `<table>`

---

## Running Tests

```bash
pytest tests/ -v
```

39 tests total across config model, calibration engine, and advisory engine (OpenAI mocked).

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Your OpenAI API key (`sk-...`) |
| `ADVISORY_MODEL` | No | Model to use (default: `gpt-4o`) |
| `ADVISORY_MAX_TOKENS` | No | Max response tokens (default: `2048`) |
| `QUOTE_API_URL` | Yes | StoneFly Quote API endpoint |
| `QUOTE_API_TOKEN` | Yes | Bearer token for Quote API |

---

## Known Limitations / Pending Work

| Item | Status | Impact |
|------|--------|--------|
| Power draw specs (idle + peak watts per chassis) | Blocked — need AIC/Chenbro model numbers from Richard | Q7 (Power Consumption) and Q9 (UPS) are estimated, not precise |
| End-to-end testing all 16 questions | Pending | Some prompt_additions YAML files may need tuning |
| Session persistence | In-memory only — restarts clear session | Not a problem for single-user local use |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| AI | OpenAI API — gpt-4o |
| HTTP client | httpx (async, for Quote API) |
| Data models | Pydantic v2 |
| Config parsing | PyYAML |
| Frontend | HTML + Vanilla JS + Tailwind CSS (CDN) |
| Streaming | SSE (Server-Sent Events) via FastAPI StreamingResponse |
| Tests | pytest, pytest-asyncio |