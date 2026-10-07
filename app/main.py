"""FastAPI backend application and API routes."""

import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from app.agent import DialogueAgent
from app.audit import get_audit_logs, init_audit_db, log_audit
from app.device_adapter import SimulatorAdapter
from app.models import (
    ApplyRequest,
    ApplyResponse,
    AuditEntry,
    DialogueRequest,
    DialogueResponse,
    DryRunRequest,
    DryRunResponse,
    HealthResponse,
    RollbackRequest,
    RollbackResponse,
    ShowRequest,
    ShowResponse,
)
from app.rag import CommandRAG
from app.simulator import MockCMGNode


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize audit database and ensure components are ready."""
    init_audit_db()
    yield

app = FastAPI(
    title="CMG Voice Configuration Backend",
    description="Text-based backend for CMG-02 network node configuration agent",
    version="1.0.0",
    lifespan=lifespan,
)

# Shared simulated environment
node = MockCMGNode(node_name="CMG-02")
adapter = SimulatorAdapter(node=node)
rag = CommandRAG()
agent = DialogueAgent(adapter=adapter, rag=rag)


@app.get("/health", response_model=HealthResponse, summary="Health Check")
def health() -> HealthResponse:
    """Return health status of the service."""
    return HealthResponse(status="ok")


@app.post("/dialogue", response_model=DialogueResponse, summary="Multi-turn Dialogue Agent")
def dialogue(req: DialogueRequest) -> DialogueResponse:
    """Process user dialogue input through agent state machine."""
    result = agent.process(session_id=req.session_id, text=req.text)
    return DialogueResponse(
        session_id=result["session_id"],
        state=result["state"],
        reply_text=result["reply_text"],
        plan=result.get("plan"),
        source=result.get("source"),
        needs=result.get("needs"),
    )


@app.post("/show", response_model=ShowResponse, summary="Read-only Command Execution")
def show(req: ShowRequest) -> ShowResponse:
    """Execute a read-only command verified against authorized RAG library."""
    # Check exact match first
    match = rag.find_exact(req.command.strip())
    if not match:
        # Search RAG with high threshold
        matches = rag.search(req.command.strip(), k=1, threshold=0.5)
        if matches:
            match = matches[0]

    if not match:
        log_audit("system", "show_failed", {"command": req.command, "error": "not found in RAG library"})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not found",
        )

    cmd = match["command"]
    source = f"{match['source_file']} -> {match['section_heading']}"
    output = adapter.show(cmd)
    log_audit("system", "show_executed", {"command": cmd, "source": source})

    return ShowResponse(output=output, source=source)


@app.post("/config/dry-run", response_model=DryRunResponse, summary="Configuration Dry-Run")
def config_dry_run(req: DryRunRequest) -> DryRunResponse:
    """Validate configuration change without altering device state."""
    res = adapter.dry_run(req.change)
    log_audit("system", "api_dry_run", {"change": req.change, "result": res})
    return DryRunResponse(
        valid=res["valid"],
        errors=res.get("errors", []),
        diff=res.get("diff", ""),
    )


@app.post("/config/apply", response_model=ApplyResponse, summary="Apply Configuration Change")
def config_apply(req: ApplyRequest) -> ApplyResponse:
    """Apply configuration with mandatory confirmation phrase guardrail."""
    if req.confirmation_phrase != "confirm":
        log_audit(
            "system",
            "apply_blocked",
            {"change": req.change, "phrase": req.confirmation_phrase},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Confirmation phrase must be exactly 'confirm'",
        )

    res = adapter.apply(req.change)
    log_audit("system", "api_apply", {"change": req.change, "result": res})
    return ApplyResponse(
        applied=res.get("applied", False),
        snapshot_id=res.get("snapshot_id"),
        detail="Applied successfully" if res.get("applied") else str(res.get("errors")),
    )


@app.post("/rollback", response_model=RollbackResponse, summary="Rollback Snapshot")
def rollback(req: RollbackRequest) -> RollbackResponse:
    """Restore state to previous snapshot."""
    res = adapter.rollback(req.snapshot_id)
    log_audit("system", "api_rollback", res)
    return RollbackResponse(
        rolled_back=res.get("rolled_back", False),
        snapshot_id=req.snapshot_id,
        message=res.get("message", ""),
    )


@app.get("/audit", response_model=List[AuditEntry], summary="Audit Log Trail")
def audit(
    session_id: Optional[str] = Query(None, description="Optional session filter"),
    limit: int = Query(50, ge=1, le=500, description="Max entries to return"),
) -> List[AuditEntry]:
    """Retrieve audit trail records in reverse chronological order."""
    logs = get_audit_logs(session_id=session_id, limit=limit)
    return [AuditEntry(**entry) for entry in logs]
