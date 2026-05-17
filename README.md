# D2C AI Employee

An AI employee for D2C brands. Connects Shopify, Shiprocket, and Meta Ads into a single normalized store, answers cross-tool questions with full source citations, and runs an autonomous P&L analysis that ranks ₹-saving actions by impact.

---

## What I Built — 5-Line Architecture

```
Connectors (Shopify / Shiprocket / Meta Ads) sync normalized rows into SQLite
Universal schema (orders / shipments / ad_spends) with provenance on every row
Chat layer: tool-use loop, 5 read tools + 3 write tools, hard citation contract
P&L Analyzer agent: trigger → Revenue / Logistics / Marketing → ranked leaks → run log
Scale harness: merchant_id partition key, SQLAlchemy pool, async-ready, PostgreSQL-swappable
```

---

## Quickstart

### Option A — Anthropic (Claude)

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Set: LLM_PROVIDER=anthropic
#      ANTHROPIC_API_KEY=sk-ant-...

# 3. Seed the database with mock data
python main.py seed

# 4. Start chat
python main.py chat

# 5. Run the P&L Analyzer agent
python main.py agent run pl

# 6. Or run as API
uvicorn main:app --reload
```

### Option B — Groq (free tier, no billing required)

```bash
cp .env.example .env
# Set: LLM_PROVIDER=groq
#      GROQ_API_KEY=gsk_...
#      GROQ_MODEL=qwen/qwen3-32b   # or any Groq model with tool-use support

python main.py seed
python main.py chat
```

Get a free Groq key at [console.groq.com](https://console.groq.com). No credit card needed.

### Switching providers

The entire chat layer is provider-agnostic. Swap the LLM by changing one env var — the tool-use loop, citation enforcement, and tool dispatch are identical for both providers.

```
LLM_PROVIDER=anthropic   # uses claude-sonnet-4-6 by default
LLM_PROVIDER=groq        # uses qwen/qwen3-32b by default
```

### Using real APIs

Set `USE_MOCK_DATA=false` in `.env` and add connector credentials. Everything works with mock data out of the box.

### API endpoints

```
POST /chat          { "message": "...", "merchant_id": "..." }
GET  /agents/pl     Run P&L Analyzer, return AgentRunLog
POST /sync          Trigger connector sync
GET  /health        Status check
```

---

## Connectors — Which 3, Why These 3

| Connector | Why |
|---|---|
| **Shopify** | ~80% of Indian D2C brands run on it. It's the revenue ground truth: orders, GMV, SKU-level performance. Without it there's no denominator for any P&L question. |
| **Shiprocket** | Logistics cost is the biggest controllable expense for D2C. NDR (non-delivery returns) is the #1 hidden cost — return shipping + RTO charges + lost COD. You can't see the leak without a shipping connector. |
| **Meta Ads** | CAC via Meta is the largest marketing spend for most D2C brands. Without it you can't answer "am I profitable per customer?" High GMV with CAC > LTV means you're funding Zuckerberg, not yourself. |

Together, these three answer the core D2C P&L question: **Revenue (Shopify) − Logistics Cost (Shiprocket) − Marketing Cost (Meta) = Contribution Margin**.

### Connector abstraction

All three implement `BaseConnector`:

```python
class BaseConnector(ABC):
    source_name: str          # 'shopify' | 'shiprocket' | 'meta_ads'
    capabilities: list[str]

    def fetch_raw(self, merchant_id, since) -> list[dict]: ...  # API call or mock
    def normalize(self, raw, merchant_id) -> list[ORM]:     ...  # → DB rows
    def sync(self, merchant_id, since) -> SyncResult:       ...  # fetch → normalize → upsert
```

`ConnectorRegistry` maps source names to classes. Adding a 4th connector = one new file + `@ConnectorRegistry.register` decorator. Core code never imports connector classes directly.

**Mock fallback:** every connector checks `USE_MOCK_DATA=true` in env. If set, `fetch_raw()` returns pre-seeded data instead of hitting real APIs. Real credentials slot in via `.env` with no code changes.

---

## Schema — Why This Shape

Every table has these non-nullable provenance columns:

```sql
merchant_id  TEXT NOT NULL   -- multi-tenancy partition key
source       TEXT NOT NULL   -- 'shopify' | 'shiprocket' | 'meta_ads'
source_id    TEXT NOT NULL   -- original ID in source system
fetched_at   TIMESTAMP NOT NULL  -- when this row was synced
raw_json     TEXT NOT NULL   -- full original payload (audit trail)
UNIQUE (merchant_id, source, source_id)  -- upsert key
```

**Why intentionally thin normalized fields + fat `raw_json`:**
Normalized fields cover exactly what the chat tools need to query and aggregate. `raw_json` covers everything else without schema migrations when sources add or rename fields. Every row is independently auditable back to the exact API response.

**Tables:** `orders`, `shipments`, `ad_spends`, `annotations` (write target — local only, never synced upstream).

---

## Chat — Tool Schema, Citation Contract, and Provider Abstraction

### LLM provider abstraction

```
chat/providers/
├── base.py        # BaseProvider ABC — ToolCall + ProviderResponse dataclasses
├── anthropic.py   # Anthropic tool format (input_schema), stop_reason="tool_use"
├── groq.py        # Groq OpenAI-compat format (parameters), finish_reason="tool_calls"
└── __init__.py    # get_provider() reads LLM_PROVIDER env var
```

The Groq provider auto-converts Anthropic's `input_schema` format to OpenAI's `parameters` format. The tool-use loop, citation enforcement, and merchant_id injection are identical for both providers — swapping LLMs requires zero code changes.

### Tools exposed to the LLM

**Read (5):**

| Tool | Queries | Returns |
|---|---|---|
| `query_orders` | `orders` table | rows + citations |
| `query_shipments` | `shipments` table | rows + citations |
| `query_ad_spends` | `ad_spends` table | rows + citations |
| `compute_metric` | aggregate query | scalar + source rows |
| `run_pl_analyzer` | P&L agent | AgentRunLog + PLSnapshot |

Available metrics: `total_revenue`, `total_ad_spend`, `ndr_rate`, `avg_shipping_cost`, `roas`, `cac`, `orders_by_status`

**Write (3):**

| Tool | Writes | Scope |
|---|---|---|
| `annotate_entity` | note + tag on any entity | local `annotations` table only |
| `flag_ndr_action` | NDR action decision (reattempt/rto/hold) | local only |
| `set_budget_recommendation` | recommended budget for a campaign | local only |

**Design note:** `merchant_id` is intentionally absent from all tool schemas. It is injected server-side by `handle_tool()` from the session context — the LLM never sees or supplies it, eliminating a class of hallucination where the model fabricates wrong merchant IDs.

### Auto-refresh — live data during chat

Each read tool transparently checks data freshness before querying the DB:

```python
def handle_tool(name, inputs, merchant_id):
    refresh_if_stale(merchant_id, "shopify")   # re-syncs connector if data is older than MAX_DATA_AGE_HOURS
    return repo.query_orders(...)
```

`db/freshness.py` compares `MAX(fetched_at)` per source against `MAX_DATA_AGE_HOURS` (default: 1 hour). If stale, it silently re-syncs the connector before the DB query runs. The LLM always sees fresh data with no extra prompting.

### How citation works (hard contract)

Every tool response returns:
```json
{
  "data": [...],
  "citations": [
    {"source": "shiprocket", "source_id": "AWB10042", "fetched_at": "...", "row_id": "uuid"}
  ]
}
```

The system prompt instructs the LLM: *every number must be followed by `[src:source:source_id]`*.

Post-processing (`chat/citations.py`) scans the response with regex for bare numbers (₹ amounts, percentages, named counts). If any found:
1. Re-submit to LLM: "These values are uncited: {list}. Add citations or remove the claims."
2. Retry up to 2 times.
3. On 3rd failure: return `{"error": "grounding_failure"}` — the user never sees an uncited number.

Example response:
> Your NDR rate is 26% [src:shiprocket:aggregate:47_shipments] for DTDC courier, compared to 5% [src:shiprocket:aggregate:96_shipments] for BlueDart.

### Tool call error handling — resilient sessions

The tool-use loop is fully exception-safe. Tool failures do not crash the chat session:

- **Provider failures** (`provider.complete()` raises): error is fed back as a system message and retried up to `MAX_PROVIDER_RETRIES=2` times. On persistent failure, returns `{"error": "provider_failure", "message": "..."}` — the REPL prints it cleanly and stays alive.
- **Tool handler failures** (`handle_tool()` raises): returns a structured error payload so the LLM can self-correct:
  ```json
  {
    "status": "tool_error",
    "tool": "query_orders",
    "error": "...",
    "hint": "Retry with corrected parameters."
  }
  ```
  The LLM sees the hint, adjusts its parameters, and retries — without the session ending.

---

## Agent — D2C P&L Analyzer

### Why this agent

A D2C founder doesn't ask "what's my NDR rate?" — they ask "am I profitable, and where am I bleeding?" The P&L Analyzer answers that in one run across all three connectors. NDR becomes a line item in logistics cost, not the whole story. It's the only agent that uses all three connectors simultaneously and surfaces ranked ₹-saving actions across every cost dimension. An NDR-only agent would answer a narrower question that is already covered as a sub-component of P&L.

### What it does

```
Trigger  : on-demand | revenue drop >10% WoW | weekly schedule
Data     : orders (GMV) + shipments (outbound + NDR return cost) + ad_spends (CAC/ROAS)
Decision : contribution margin = net_revenue - logistics - marketing
           rank leaks: high-NDR courier | low-ROAS campaign | high-return SKU
Action   : top 3 recommendations with ₹ savings estimate per period
Output   : AgentRunLog JSON — full reasoning chain, no side effects, nothing sent upstream
```

### Run log structure

```python
@dataclass
class AgentRunLog:
    agent_name: str
    merchant_id: str
    run_at: datetime
    trigger_condition: str       # "on-demand" | "revenue_drop" | "weekly"
    trigger_met: bool
    pl_snapshot: PLSnapshot      # every number carries citations
    reasoning_steps: list[str]   # numbered chain-of-thought
    leaks: list[dict]            # ranked by ₹ impact
    recommendations: list[dict]  # top 3 with estimated_savings_inr
    confidence: str              # "high" | "medium" | "low"
    failure_modes_hit: list[str]
```

### Sample output (ZapBold mock data, last 30 days)

```
Step 7: Contribution margin = ₹296,584 - ₹16,153 - ₹59,764 = ₹220,667 (74.4%)
Leak 1: Campaign 'Broad — Awareness' ROAS 1.30 < 1.5 threshold → pause → save ₹19,985
Leak 2: SKU 'Sneaker Black 42' 14% return rate → investigate sizing → save ₹3,598
Leak 3: DTDC 26% NDR → switch to BlueDart in Mumbai/Pune pincodes → save ₹650
```

### Failure modes (documented upfront)

| Mode | Condition | Effect |
|---|---|---|
| `insufficient_orders` | < 50 orders in window | confidence = "low" |
| `missing_connector` | any source has 0 rows | P&L marked partial |
| `attribution_gap` | orders not matched to shipments | logistics cost may be underestimated |
| `meta_attribution_overlap` | Meta `revenue_attributed` uses last-click | may double-count organic orders |
| `seasonal_distortion` | period includes sale event | margins unrepresentative |
| `single_courier_data` | only 1 courier in data | cannot recommend courier switch |

---

## Mock Data — ZapBold

The seed data (`mock_data.py`) represents a fictional D2C footwear brand "ZapBold". It is designed to tell a clear P&L story:

- **500 orders** over 60 days, ~₹1,200 avg order value
- **420 shipments** across 4 couriers:
  - Delhivery: 8% NDR
  - BlueDart: 5% NDR (premium, lowest returns)
  - DTDC: 28% NDR — concentrated in Mumbai West + Pune pincodes (the villain)
  - Xpressbees: 12% NDR
- **3 Meta campaigns over 60 days:**
  - Retargeting: ₹30k spend, ROAS 4.2 (keep)
  - Lookalike: ₹50k spend, ROAS 2.1 (ok)
  - Broad Awareness: ₹40k spend, ROAS 1.3 (burning money — below 1.5 threshold)

`random.seed(42)` makes data deterministic — same numbers every `python main.py seed`.

---

## Scale — 1 Merchant to 10,000

### Built into v0

| What | How |
|---|---|
| Multi-tenancy | `merchant_id` non-nullable partition key on every table, day one |
| PostgreSQL-ready | SQLAlchemy ORM — swap SQLite → PostgreSQL via one env var (`DATABASE_URL`) |
| Connection pooling | `pool_size=10, max_overflow=20, pool_timeout=30` (SQLite: `pool_size=5`) |
| WAL mode | SQLite `PRAGMA journal_mode=WAL` reduces write contention |
| Async-ready | `httpx.AsyncClient` per connector; sync loop is `await`-able |
| Rate limiting | Token bucket per connector (configurable `RPM` via env) |

### What breaks at 10k merchants

| What breaks | Why | Fix |
|---|---|---|
| SQLite | Single writer, file lock. 10k hourly syncs = contention | PostgreSQL |
| Sync loop | Sequential `for merchant in all_merchants` takes hours | Celery + Redis, merchant-ID-sharded queues |
| Chat history | In-memory dict, lost on restart | DB-backed `chat_sessions` table |
| Meta Ads rate limits | 200 API calls/hour per app token — hits cap at ~200 merchants/hour | Per-merchant OAuth tokens |
| LLM API | Concurrent sessions hit rate limits | Request queue + streaming responses |
| Cold syncs | New merchant = full history pull | Cursor-based incremental sync (`updated_at_min`) |

The first thing that breaks is **SQLite at ~50 concurrent merchants writing simultaneously**. Everything else follows from that.

---

## Eval — Where It Breaks

1. **Citation regex is brittle.** Catches `₹1,200` and `28%` but misses "1.2 lakh" or "a few thousand". Edge cases exist.

2. **NDR return cost is hardcoded at ₹65/return.** Real cost varies by courier contract and zone. The savings estimate is directionally correct, not exact.

3. **Meta attribution is last-click.** `revenue_attributed` may double-count orders that were organic but also saw an ad. Contribution margin could be overstated.

4. **Mock data is deterministic (seed=42).** Real merchant data will have missing fields, inconsistent courier name spelling ("DTDC" vs "Dtdc"), Unicode issues in pincodes.

5. **No auth.** `merchant_id` is a parameter, not from a JWT. Multi-tenant isolation is logical (every query filters by `merchant_id`), not enforced at the DB connection level.

6. **Chat history is session-only.** No memory across conversations. Each new `chat_repl` starts fresh.

7. **Sync is pull-only.** No webhooks. Data is as fresh as the last sync. A Shopify order placed 2 minutes ago won't appear in chat until the next auto-refresh cycle.

8. **SKU return rate requires `raw_json` parse.** If `line_items` is missing from `raw_json` (some Shopify API variants), the SKU analysis silently skips those orders.

9. **Groq free tier token limits.** The free plan caps tokens per request. If you hit a 413 error, switch to a Groq model with a higher context limit (e.g. `moonshotai/kimi-k2-instruct`) or use the Anthropic provider.

---

## Hours Spent

| Session | Work |
|---|---|
| Session 1 (~3 hrs) | Read assignment, plan, scaffold, DB models, all 3 connectors, mock data, seed, chat tools, citation enforcer, tool-use loop, P&L agent, FastAPI, CLI, tests (30 passing), README, eval section |
| Session 2 (~3 hrs) | Groq provider abstraction (swappable LLM), auto-refresh, tool call error handling, model updates, README update |

**Total: ~6 hours across 2 sessions.**

---

## What I'd Do With Another Week

1. **Real API credentials + live demo.** Wire up actual Shopify dev store, Shiprocket sandbox, Meta test account. The mock data tells the right story but a live merchant is more compelling.

2. **Webhook-based sync.** Shopify and Shiprocket both offer webhooks. Replace the pull loop with push events — data freshness goes from "minutes" to "seconds".

3. **Chat memory across sessions.** Store conversation history in a `chat_sessions` table. The agent should remember "you asked about DTDC last week" and surface follow-up.

4. **PostgreSQL + Celery migration.** Set up the actual queue infrastructure, not just the ORM-level readiness. Prove the scale harness runs at >100 concurrent merchants.

5. **LTV model.** Add `customers` table, compute LTV from repeat purchase rate, wire CAC vs LTV comparison into the P&L agent. Right now we compare spend to session-attributed revenue, not lifetime value.

6. **Richer citation UI.** Instead of `[src:shopify:5042]` in Markdown, return structured citations that a frontend can render as clickable source links.

---

## A Note on AI Tools

Claude (claude-sonnet-4-6) was used throughout this build:
- **Code generation**: SQLAlchemy models, FastAPI endpoints, connector skeletons, test scaffolding
- **Architecture feedback**: discussing tradeoffs on schema shape, citation enforcement design, provider abstraction

**I wrote / decided:**
- Connector choices (Shopify + Shiprocket + Meta Ads) and the reasoning behind them
- Agent choice (P&L Analyzer over a narrower NDR-only agent)
- The citation enforcement design — hard block, not a warning
- The leak-ranking algorithm and the ZapBold mock data story
- The README reasoning sections — the "why" throughout

The code structure reflects judgment calls about what matters for this assignment. AI generated the boilerplate; the decisions about what to build are mine.

---

## Project Structure

```
D2C-AI-Employee/
├── connectors/
│   ├── base.py          # BaseConnector ABC + ConnectorRegistry (swappable)
│   ├── shopify.py       # Shopify REST Admin API 2024-01
│   ├── shiprocket.py    # Shiprocket JWT auth + pagination
│   └── meta_ads.py      # Meta Marketing API v18 + facebook-business SDK
├── db/
│   ├── models.py        # Universal schema — provenance on every row
│   ├── session.py       # SQLAlchemy engine + WAL + connection pool
│   ├── repository.py    # All query + write methods (single data access layer)
│   └── freshness.py     # Auto-refresh: re-syncs stale sources before chat queries
├── chat/
│   ├── agent.py         # Tool-use loop — provider-agnostic, resilient error handling
│   ├── tools.py         # 5 read + 3 write tool definitions + handlers
│   ├── citations.py     # Hard citation enforcement (regex scan + retry loop)
│   └── providers/
│       ├── base.py      # BaseProvider ABC — ToolCall + ProviderResponse dataclasses
│       ├── anthropic.py # Anthropic Claude (tool-use format)
│       ├── groq.py      # Groq / Llama (OpenAI-compat format, auto-converts schemas)
│       └── __init__.py  # get_provider() — reads LLM_PROVIDER env var
├── agents/
│   ├── base.py          # BaseAgent ABC + AgentRunLog dataclass
│   └── pl_analyzer.py   # D2C P&L Analyzer — explicit failure modes documented
├── tests/               # 30 tests — connectors, citations, P&L agent
├── mock_data.py         # ZapBold seed data (realistic D2C footwear brand)
├── seed.py              # Loads mock data into DB via connectors
├── main.py              # CLI (seed / sync / chat / agent) + FastAPI app
├── .env.example         # All config — copy to .env and fill in keys
└── requirements.txt
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `USE_MOCK_DATA` | `true` | Use seed data instead of real APIs |
| `MERCHANT_ID` | `zapbold-001` | Merchant to query in CLI mode |
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `groq` |
| `ANTHROPIC_API_KEY` | — | Required if `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Anthropic model ID |
| `GROQ_API_KEY` | — | Required if `LLM_PROVIDER=groq` |
| `GROQ_MODEL` | `qwen/qwen3-32b` | Groq model ID |
| `DATABASE_URL` | `sqlite:///d2c.db` | SQLite or PostgreSQL |
| `MAX_DATA_AGE_HOURS` | `1` | Hours before a source is re-synced during chat |
| `NDR_THRESHOLD` | `0.15` | NDR rate above which courier is flagged |
| `ROAS_THRESHOLD` | `1.5` | ROAS below which campaign is flagged |
