# CMG Voice Configuration Agent - Backend

Text-based backend for a simulated "Voice-Based Configuration Agent" targeting network element `CMG-02`. Built with Python 3.11+, FastAPI, ChromaDB, and sentence-transformers.

---

## Architecture & Guarantees

- **Fully Simulated:** All operations run strictly in-memory (`MockCMGNode`). No SSH, telnet, or real network connections are ever opened.
- **Fictional Data Only:** Target node is named `CMG-02`, and all IP addresses are fictional `10.0.0.x`.
- **Zero Invented Commands:** Every command and template is retrieved directly from an indexed RAG library of approved health check and configuration procedures. Every answer displays its exact file and section source.
- **Automated Safety Guardrails:**
  - **Read-Only by Default:** Configuration changes require explicit confirmation in the `AWAITING_CONFIRM` state.
  - **Confirmation Guard:** `/config/apply` strictly refuses execution unless the confirmation phrase is exactly `"confirm"`.
  - **Blocklist Filtering:** Hazardous commands (e.g. `reboot`, `rm -rf`, `format`, `factory-default`) are rejected immediately.
  - **Single Operation Rule:** Only one configuration change per request is permitted.
  - **Automatic Rollback:** State snapshots are taken prior to applying changes. If post-apply verification fails, the node automatically rolls back to the previous snapshot.
  - **Strict Node Validation:** Only `CMG-02` is accepted; requests for other nodes are rejected.
  - **Sanitisation:** Sensitive operator names (`VIL`, `Vodafone Idea`, etc.) in titles and notes are sanitised to neutral terms during ingestion.
  - **Complete Audit Trail:** Every step (intent parsed, RAG lookup, dry-run, confirm, apply, verify, rollback, block, cancel) is recorded in SQLite (`data/audit.db`).

---

## Directory Layout

```
cmg_agent/
  app/
    main.py            # FastAPI app and API routes
    simulator.py       # MockCMGNode in-memory simulator
    device_adapter.py  # DeviceAdapter ABC and SimulatorAdapter
    parser.py          # Plain-text health-check and template parser
    rag.py             # ChromaDB persistent indexing and retrieval
    agent.py           # Dialogue state machine and safety guardrails
    audit.py           # SQLite audit logging
    models.py          # Pydantic request and response models
  data/
    raw/               # Plain-text health check files and config templates
    blocklist.txt      # Blocked dangerous commands
    audit.db           # SQLite audit database (created at runtime)
  scripts/
    ingest.py          # Ingests data/raw/*.txt into ChromaDB
  tests/
    test_parser.py     # Parser and sanitisation tests
    test_simulator.py  # Simulator and adapter unit tests
    test_rag.py        # ChromaDB indexing and semantic search tests
    test_dialogue.py   # Multi-turn dialogue state machine tests (Flows 1-7)
    test_api.py        # FastAPI endpoint integration tests
  README.md
  requirements.txt
```

---

## Setup & Installation

### 1. Create Virtual Environment
```bash
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Ingest Command Library
Populate the ChromaDB vector database from `data/raw/`:
```bash
python scripts/ingest.py
```

### 4. Run the Test Suite
```bash
pytest tests/ -v
```

### 5. Launch the FastAPI Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Interactive OpenAPI documentation will be available at `http://localhost:8000/docs`.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check (`{"status": "ok"}`) |
| `POST` | `/dialogue` | Multi-turn conversational agent (`{session_id, text}`) |
| `POST` | `/show` | Read-only command execution with verified RAG source |
| `POST` | `/config/dry-run` | Dry-run change validation with diff |
| `POST` | `/config/apply` | Apply change (requires `confirmation_phrase: "confirm"`) |
| `POST` | `/rollback` | Restore state to a given `snapshot_id` |
| `GET` | `/audit` | Query audit trail (newest first, optional `session_id`) |

---

## Multi-Turn Dialogue Examples

### Show Health Check
```json
// POST /dialogue
{ "session_id": "s1", "text": "Show BGP neighbour summary on CMG-02" }
```
**Response:**
Returns output showing 3 peers (2 Established, 1 Active) along with source metadata.

### Configuration with Dry-Run & Confirmation
```json
// Turn 1: POST /dialogue
{ "session_id": "s2", "text": "Set MTU 1500 on interface ge-0/0/1 of CMG-02" }
```
**Response:** State transitions to `AWAITING_CONFIRM` with diff `- mtu 9000 \n + mtu 1500`. No change applied yet.

```json
// Turn 2: POST /dialogue
{ "session_id": "s2", "text": "confirm" }
```
**Response:** State transitions to `DONE`. Change applied, verified, and snapshot ID returned.
