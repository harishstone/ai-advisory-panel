import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from core.advisory_engine import AdvisoryEngine
from core.session_store import SessionStore
from core.quote_import import QuoteImporter

load_dotenv()

app = FastAPI(title="AI Advisory Panel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = AdvisoryEngine()
store = SessionStore.get()
importer = QuoteImporter()


# ─── Request Models ────────────────────────────────────────────────────────────

class LoadQuoteRequest(BaseModel):
    quote_number: str

class AskQuestionRequest(BaseModel):
    question_id: Optional[int] = None   # 1–16 for pre-selected, None for custom
    custom_question: Optional[str] = None


# ─── Endpoint 1: Load Quote ────────────────────────────────────────────────────

@app.post("/api/load-quote")
async def load_quote(req: LoadQuoteRequest):
    """
    Fetch quote details from the Product Configurator API using the quote number,
    map the response to ApplianceConfig, and store in session.
    """
    try:
        config = await importer.fetch_and_map(req.quote_number)
        store.set_config(config)
        loaded_sections = [
            s for s in ["profile", "compute", "storage_media",
                         "storage_config", "network", "veeam", "environment"]
            if getattr(config, s) is not None
        ]
        return {
            "success": True,
            "quote_number": req.quote_number,
            "sections_loaded": loaded_sections,
            "config_summary": config.model_dump(exclude_none=True)
        }
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Endpoint 2: List Pre-Selected Questions ──────────────────────────────────

@app.get("/api/questions")
def list_questions():
    """Return all 16 pre-selected questions."""
    return {
        "questions": [
            {"id": 1,  "text": "What IOPS, Read Throughput and Write Throughput can I expect for iSCSI, NAS (CIFS/NFS), S3?"},
            {"id": 2,  "text": "What Restore Rate/Speed can I expect from a Veeam Backup Restore (File-Level vs Image-Level)?"},
            {"id": 3,  "text": "What Backup Speed will I get on Veeam Backups and Backup Copy Jobs?"},
            {"id": 4,  "text": "What network throughput for data transfer: Single NIC vs LACP/Bonding?"},
            {"id": 5,  "text": "What is the Best RAID Configuration for my disks across different workload types?"},
            {"id": 6,  "text": "What is the Rebuild Time when a disk fails and the Hot Spare kicks in?"},
            {"id": 7,  "text": "What is the expected Power Consumption of the appliance?"},
            {"id": 8,  "text": "How many Rack Units (U) are required for my appliance?"},
            {"id": 9,  "text": "What are the recommended UPS specifications?"},
            {"id": 10, "text": "SSD Sizing for an SNSD S3 volume — how much SSD is needed?"},
            {"id": 11, "text": "Storage Efficiency — what savings can I expect from deduplication?"},
            {"id": 12, "text": "Deduplication Index Resource sizing for my volume?"},
            {"id": 13, "text": "Resources needed for concurrent Veeam Backup/Copy/Replication jobs?"},
            {"id": 14, "text": "Cache Storage Size for FC index for my backing resource?"},
            {"id": 15, "text": "What bonding mode gives the best performance vs redundancy trade-off?"},
            {"id": 16, "text": "How much usable backup storage do I need for my VMs?"},
        ]
    }


# ─── Endpoint 3: Ask a Question ───────────────────────────────────────────────

@app.post("/api/ask")
def ask_question(req: AskQuestionRequest):
    """
    Ask a pre-selected (Category A) or custom (Category B) question.
    Requires a quote to be loaded first via /api/load-quote.
    """
    if not store.has_config():
        raise HTTPException(
            status_code=400,
            detail="No quote loaded. Call /api/load-quote first."
        )

    if req.question_id is not None:
        if not 1 <= req.question_id <= 16:
            raise HTTPException(status_code=400, detail="question_id must be 1–16.")
        result = engine.ask_preselected(req.question_id)
    elif req.custom_question and req.custom_question.strip():
        result = engine.ask_custom(req.custom_question.strip())
    else:
        raise HTTPException(status_code=400, detail="Provide question_id or custom_question.")

    return {
        "category": result["category"],
        "question": result["question"],
        "response": result["response"],
        "calibration_warnings": result.get("calibration_warnings", [])
    }


# ─── Endpoint 4: Ask a Question (Streaming) ───────────────────────────────────

@app.post("/api/ask-stream")
async def ask_question_stream(req: AskQuestionRequest):
    """Streaming version of /api/ask — sends tokens via SSE as they are generated."""
    if not store.has_config():
        raise HTTPException(status_code=400, detail="No quote loaded. Call /api/load-quote first.")

    if req.question_id is not None:
        if not 1 <= req.question_id <= 16:
            raise HTTPException(status_code=400, detail="question_id must be 1–16.")
        gen = engine.ask_preselected_stream(req.question_id)
    elif req.custom_question and req.custom_question.strip():
        gen = engine.ask_custom_stream(req.custom_question.strip())
    else:
        raise HTTPException(status_code=400, detail="Provide question_id or custom_question.")

    async def event_generator():
        async for event in gen:
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ─── Endpoint 5: Get Config Summary ───────────────────────────────────────────

@app.get("/api/config-summary")
def config_summary():
    config = store.get_config()
    if not config:
        raise HTTPException(status_code=404, detail="No quote loaded.")
    return config.model_dump(exclude_none=True)


# ─── Endpoint 5: Clear Session ────────────────────────────────────────────────

@app.post("/api/clear")
def clear_session():
    store.clear()
    return {"success": True, "message": "Session cleared."}


# ─── Serve Frontend ───────────────────────────────────────────────────────────

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
