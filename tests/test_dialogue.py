"""Tests for DialogueAgent state machine and dialogue flows."""

import shutil
import tempfile
import pytest
from app.agent import DialogueAgent
from app.device_adapter import SimulatorAdapter
from app.rag import CommandRAG
from app.simulator import MockCMGNode


@pytest.fixture
def agent_fixture():
    """Create fresh isolated node, adapter, RAG and dialogue agent."""
    temp_dir = tempfile.mkdtemp()
    rag = CommandRAG(persist_dir=temp_dir, collection_name="agent_test_commands")
    test_chunks = [
        {
            "id": "c1",
            "source_file": "health_check_core.txt",
            "section_heading": "To check BGP status, they must be UP and connected",
            "command": "show router bgp summary",
            "note": "bgp check",
        },
        {
            "id": "c2",
            "source_file": "config_templates.txt",
            "section_heading": "Set MTU on an interface",
            "command": "configure port {interface} ethernet mtu {value}",
            "note": "",
        },
    ]
    rag.index_chunks(test_chunks)

    node = MockCMGNode(node_name="CMG-02")
    adapter = SimulatorAdapter(node)
    agent = DialogueAgent(adapter=adapter, rag=rag)

    yield agent, node, adapter, rag
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_dialogue_flow_1_show_bgp(agent_fixture) -> None:
    """Flow 1: Show BGP neighbour summary on CMG-02 -> 3 peers, one down, with source."""
    agent, node, adapter, rag = agent_fixture
    res = agent.process("sess_1", "Show BGP neighbour summary on CMG-02")

    assert res["state"] == "IDLE"
    assert "health_check_core.txt" in res["source"]
    assert "CMG-02" in res["reply_text"]
    assert "Total Peers     : 3" in res["reply_text"]
    assert "Peers Up       : 2" in res["reply_text"]
    assert "Active" in res["reply_text"]


def test_dialogue_flow_2_and_3_set_mtu_and_confirm(agent_fixture) -> None:
    """Flow 2 & 3: Set MTU 1500 plan with diff, then confirm applies and verifies."""
    agent, node, adapter, rag = agent_fixture

    # Step 1: propose change
    res1 = agent.process("sess_2", "Set MTU 1500 on interface ge-0/0/1 of CMG-02")
    assert res1["state"] == "AWAITING_CONFIRM"
    assert res1["plan"] is not None
    assert "- mtu 9000" in res1["plan"]
    assert "+ mtu 1500" in res1["plan"]
    assert "Say 'confirm'" in res1["reply_text"]
    # Verify no state change yet
    assert node.interfaces["ge-0/0/1"]["mtu"] == 9000

    # Step 2: confirm
    res2 = agent.process("sess_2", "confirm")
    assert res2["state"] == "DONE"
    assert "applied and verified successfully" in res2["reply_text"]
    assert "Snapshot ID:" in res2["reply_text"]
    # Node state updated
    assert node.interfaces["ge-0/0/1"]["mtu"] == 1500


def test_dialogue_flow_4_set_mtu_then_cancel(agent_fixture) -> None:
    """Flow 4: Set MTU proposed then cancelled leaves state unchanged."""
    agent, node, adapter, rag = agent_fixture

    res1 = agent.process("sess_3", "Set MTU 1500 on interface ge-0/0/1 of CMG-02")
    assert res1["state"] == "AWAITING_CONFIRM"

    res2 = agent.process("sess_3", "cancel")
    assert res2["state"] == "IDLE"
    assert "cancelled" in res2["reply_text"]
    assert node.interfaces["ge-0/0/1"]["mtu"] == 9000


def test_dialogue_flow_5_missing_details(agent_fixture) -> None:
    """Flow 5: Set MTU with no details prompts for interface and value."""
    agent, node, adapter, rag = agent_fixture

    res1 = agent.process("sess_4", "Set MTU")
    assert res1["state"] == "NEED_DETAILS"
    assert "interface" in res1["needs"]
    assert "value" in res1["needs"]
    assert "specify" in res1["reply_text"]

    # Provide missing details in next turn
    res2 = agent.process("sess_4", "interface ge-0/0/1 mtu 1500")
    assert res2["state"] == "AWAITING_CONFIRM"
    assert "- mtu 9000" in res2["plan"]


def test_dialogue_flow_6_reboot_blocked(agent_fixture) -> None:
    """Flow 6: Reboot the node is blocked by safety policy."""
    agent, node, adapter, rag = agent_fixture

    res = agent.process("sess_5", "Reboot the node")
    assert "blocked" in res["reply_text"].lower()


def test_dialogue_flow_7_forced_verify_failure_automatic_rollback(agent_fixture) -> None:
    """Flow 7: Forced verify failure triggers automatic rollback."""
    agent, node, adapter, rag = agent_fixture

    agent.process("sess_6", "Set MTU 1500 on interface ge-0/0/1 of CMG-02")
    # Force verification failure on node
    node.force_verify_failure = True

    res = agent.process("sess_6", "confirm")
    assert "Verification failed" in res["reply_text"]
    assert "Automatically rolled back" in res["reply_text"]
    assert node.interfaces["ge-0/0/1"]["mtu"] == 9000


def test_dialogue_flow_unindexed_query_returns_not_found(agent_fixture) -> None:
    """Unindexed query like 'What's the weather' returns 'not found'."""
    agent, node, adapter, rag = agent_fixture
    res = agent.process("sess_weather", "What's the weather")
    assert res["state"] == "IDLE"
    assert "not found" in res["reply_text"].lower()
