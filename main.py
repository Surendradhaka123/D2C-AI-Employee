"""
D2C AI Employee — entry point.

CLI:
    python main.py seed [--reset]          Seed the DB with mock data
    python main.py sync [--connector NAME] Sync connectors
    python main.py chat                    Interactive chat REPL
    python main.py agent run pl            Run P&L Analyzer agent

FastAPI:
    uvicorn main:app --reload
    POST /sync       { merchant_id }
    POST /chat       { merchant_id, message, history? }
    GET  /agents/pl  ?merchant_id=zapbold-001
    GET  /health
"""

import json
import os
import sys

os.environ.setdefault("USE_MOCK_DATA", "true")

from dotenv import load_dotenv
load_dotenv()

# ── CLI ──────────────────────────────────────────────────────────────────────

def cli() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    merchant_id = os.getenv("MERCHANT_ID", "zapbold-001")
    cmd = args[0]

    if cmd == "seed":
        import seed as seed_module
        seed_module.seed(reset="--reset" in args)

    elif cmd == "sync":
        import connectors
        from connectors.base import ConnectorRegistry
        from db.session import init_db
        init_db()
        names = [args[2]] if "--connector" in args and len(args) > 2 else ConnectorRegistry.names()
        for name in names:
            result = ConnectorRegistry.get(name).sync(merchant_id)
            print(result)

    elif cmd == "chat":
        from chat.agent import chat_repl
        chat_repl(merchant_id)

    elif cmd == "agent" and len(args) >= 3 and args[1] == "run" and args[2] == "pl":
        from agents.pl_analyzer import PLAnalyzerAgent
        log = PLAnalyzerAgent().run(merchant_id)
        print(json.dumps(log.to_dict(), indent=2))

    else:
        print(f"Unknown command: {' '.join(args)}")
        print(__doc__)


# ── FastAPI ──────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="D2C AI Employee", version="0.1.0")


class SyncRequest(BaseModel):
    merchant_id: str = "zapbold-001"
    connector: str | None = None


class ChatRequest(BaseModel):
    merchant_id: str = "zapbold-001"
    message: str
    history: list[dict] | None = None


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/sync")
def sync(req: SyncRequest):
    import connectors
    from connectors.base import ConnectorRegistry
    from db.session import init_db
    init_db()

    results = []
    names = [req.connector] if req.connector else ConnectorRegistry.names()
    for name in names:
        result = ConnectorRegistry.get(name).sync(req.merchant_id)
        results.append({"source": result.source, "rows_written": result.rows_written, "errors": result.errors})
    return {"results": results}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    from chat.agent import chat
    result = chat(req.merchant_id, req.message, req.history)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result)
    return result


@app.get("/agents/pl")
def run_pl_agent(merchant_id: str = "zapbold-001", period_days: int = 30):
    from agents.pl_analyzer import PLAnalyzerAgent
    log = PLAnalyzerAgent().run(merchant_id, period_days=period_days)
    return log.to_dict()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
