"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
from app.main import app, agent, node, rag


@pytest.fixture(scope="module", autouse=True)
def setup_api_data() -> None:
    """Populate RAG index for API tests."""
    test_chunks = [
        {
            "id": "api_c1",
            "source_file": "health_check_core.txt",
            "section_heading": "To check BGP status, they must be UP and connected",
            "command": "show router bgp summary",
            "note": "bgp check",
        },
        {
            "id": "api_c2",
            "source_file": "config_templates.txt",
            "section_heading": "Set MTU on an interface",
            "command": "configure port {interface} ethernet mtu {value}",
            "note": "",
        },
    ]
    rag.index_chunks(test_chunks)


@pytest.fixture
def client() -> TestClient:
    """Return FastAPI TestClient."""
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    """Test /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_show_endpoint_valid_command(client: TestClient) -> None:
    """Test /show with valid indexed command."""
    response = client.post("/show", json={"command": "show router bgp summary"})
    assert response.status_code == 200
    data = response.json()
    assert "BGP Router Summary for Node: CMG-02" in data["output"]
    assert "health_check_core.txt" in data["source"]


def test_show_endpoint_unindexed_command_returns_404(client: TestClient) -> None:
    """Test /show with unindexed command returns 404."""
    response = client.post("/show", json={"command": "show mysterious alien protocol"})
    assert response.status_code == 404
    assert response.json()["detail"] == "not found"


def test_config_dry_run_endpoint(client: TestClient) -> None:
    """Test /config/dry-run endpoint."""
    response = client.post(
        "/config/dry-run",
        json={"change": {"type": "set_mtu", "interface": "ge-0/0/1", "value": 1500}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert "- mtu 9000" in data["diff"]


def test_config_apply_refuses_without_confirm_phrase(client: TestClient) -> None:
    """Test /config/apply refuses with 403 unless confirmation_phrase is 'confirm'."""
    response = client.post(
        "/config/apply",
        json={
            "change": {"type": "set_mtu", "interface": "ge-0/0/1", "value": 1500},
            "confirmation_phrase": "please apply",
        },
    )
    assert response.status_code == 403


def test_config_apply_and_rollback(client: TestClient) -> None:
    """Test /config/apply with 'confirm' and /rollback."""
    response = client.post(
        "/config/apply",
        json={
            "change": {"type": "set_mtu", "interface": "ge-0/0/1", "value": 1500},
            "confirmation_phrase": "confirm",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["applied"] is True
    snapshot_id = data["snapshot_id"]

    # Roll back
    rb_res = client.post("/rollback", json={"snapshot_id": snapshot_id})
    assert rb_res.status_code == 200
    assert rb_res.json()["rolled_back"] is True


def test_dialogue_and_audit_endpoints(client: TestClient) -> None:
    """Test /dialogue endpoint and verify steps recorded in /audit."""
    session_id = "test_audit_session_99"

    # Turn 1: Show BGP
    res1 = client.post("/dialogue", json={"session_id": session_id, "text": "show bgp"})
    assert res1.status_code == 200
    assert "CMG-02" in res1.json()["reply_text"]

    # Turn 2: Set MTU
    res2 = client.post(
        "/dialogue",
        json={"session_id": session_id, "text": "Set MTU 1500 on interface ge-0/0/1 of CMG-02"},
    )
    assert res2.status_code == 200
    assert res2.json()["state"] == "AWAITING_CONFIRM"

    # Turn 3: Confirm
    res3 = client.post("/dialogue", json={"session_id": session_id, "text": "confirm"})
    assert res3.status_code == 200
    assert res3.json()["state"] == "DONE"

    # Fetch audit
    audit_res = client.get(f"/audit?session_id={session_id}")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert len(audit_data) > 0

    steps_recorded = {entry["step"] for entry in audit_data}
    assert "intent_parsed" in steps_recorded
    assert "confirm" in steps_recorded
    assert "apply" in steps_recorded
    assert "verify" in steps_recorded
