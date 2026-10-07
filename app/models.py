"""Pydantic models for request and response validation."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DialogueRequest(BaseModel):
    """Request payload for dialogue endpoint."""
    session_id: str = Field(..., description="Unique conversation session identifier")
    text: str = Field(..., description="User input text")


class DialogueResponse(BaseModel):
    """Response payload for dialogue endpoint."""
    session_id: str
    state: str
    reply_text: str
    plan: Optional[str] = None
    source: Optional[str] = None
    needs: Optional[List[str]] = None


class ShowRequest(BaseModel):
    """Request payload for read-only command execution."""
    command: str = Field(..., description="Command to execute")


class ShowResponse(BaseModel):
    """Response payload containing command output and verified RAG source."""
    output: str
    source: str


class ChangePayload(BaseModel):
    """Configuration change payload."""
    type: str = Field(..., description="Change type: set_mtu, interface_admin, save_config")
    interface: Optional[str] = Field(None, description="Interface name (e.g., ge-0/0/1)")
    value: Optional[int] = Field(None, description="Numeric value, e.g., MTU")
    state: Optional[str] = Field(None, description="Admin state: up/down/shutdown/no shutdown")
    node: Optional[str] = Field(None, description="Target node name, must be CMG-02")


class DryRunRequest(BaseModel):
    """Request payload for dry-run config validation."""
    change: Dict[str, Any] = Field(..., description="Dictionary describing the proposed change")


class DryRunResponse(BaseModel):
    """Response payload for dry-run simulation."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    diff: str = ""


class ApplyRequest(BaseModel):
    """Request payload for applying configuration."""
    change: Dict[str, Any] = Field(..., description="Dictionary describing the change to apply")
    confirmation_phrase: str = Field(..., description="Must be exactly 'confirm'")


class ApplyResponse(BaseModel):
    """Response payload for applied configuration."""
    applied: bool
    snapshot_id: Optional[str] = None
    detail: Optional[str] = None


class RollbackRequest(BaseModel):
    """Request payload for rolling back to a previous snapshot."""
    snapshot_id: str = Field(..., description="Snapshot identifier to restore")


class RollbackResponse(BaseModel):
    """Response payload for rollback operation."""
    rolled_back: bool
    snapshot_id: str
    message: str


class AuditEntry(BaseModel):
    """Record in the audit trail."""
    id: int
    ts: str
    session_id: str
    step: str
    detail_json: str


class HealthResponse(BaseModel):
    """Service health response."""
    status: str
