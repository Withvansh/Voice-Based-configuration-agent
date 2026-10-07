"""Tests for MockCMGNode simulator and SimulatorAdapter."""

import pytest
from app.device_adapter import SimulatorAdapter
from app.simulator import MockCMGNode


def test_simulator_show_commands() -> None:
    """Test show command outputs and table formatting."""
    node = MockCMGNode()

    # BGP summary
    bgp_out = node.show("show router bgp summary")
    assert "BGP Router Summary for Node: CMG-02" in bgp_out
    assert "10.0.0.10" in bgp_out
    assert "Active" in bgp_out
    assert "Established" in bgp_out

    # Interface table
    iface_out = node.show("show router interface")
    assert "Interface Table" in iface_out
    assert "ge-0/0/1" in iface_out

    # System alarms
    alarm_out = node.show("show system alarm")
    assert "ALM-104" in alarm_out

    # NTP
    ntp_out = node.show("show system ntp")
    assert "Synchronized" in ntp_out

    # PDN statistics
    pdn_out = node.show("show mobile-gateway pdn statistics summary")
    assert "Total PDN Sessions" in pdn_out

    # Unsupported command
    unsupported = node.show("show chassis hardware")
    assert "command not supported by simulator" in unsupported


def test_dry_run_does_not_change_state() -> None:
    """Verify that dry_run generates diff without altering node state."""
    node = MockCMGNode()
    initial_mtu = node.interfaces["ge-0/0/1"]["mtu"]

    change = {"type": "set_mtu", "interface": "ge-0/0/1", "value": 1500}
    res = node.dry_run(change)

    assert res["valid"] is True
    assert "- mtu 9000" in res["diff"]
    assert "+ mtu 1500" in res["diff"]
    # State remains untouched
    assert node.interfaces["ge-0/0/1"]["mtu"] == initial_mtu


def test_dry_run_rejects_invalid_mtu() -> None:
    """Verify that MTUs outside 576-9216 or non-existent interfaces are rejected."""
    node = MockCMGNode()

    # Too small MTU
    res_small = node.dry_run({"type": "set_mtu", "interface": "ge-0/0/1", "value": 500})
    assert res_small["valid"] is False
    assert any("Invalid MTU" in err for err in res_small["errors"])

    # Too large MTU
    res_large = node.dry_run({"type": "set_mtu", "interface": "ge-0/0/1", "value": 10000})
    assert res_large["valid"] is False

    # Unknown interface
    res_unknown = node.dry_run({"type": "set_mtu", "interface": "ge-9/9/9", "value": 1500})
    assert res_unknown["valid"] is False
    assert any("not found" in err for err in res_unknown["errors"])


def test_apply_and_rollback() -> None:
    """Verify apply changes state and snapshot rollback restores original state."""
    node = MockCMGNode()
    assert node.interfaces["ge-0/0/1"]["mtu"] == 9000

    change = {"type": "set_mtu", "interface": "ge-0/0/1", "value": 1500}
    apply_res = node.apply(change)
    assert apply_res["applied"] is True
    snapshot_id = apply_res["snapshot_id"]

    # State changed
    assert node.interfaces["ge-0/0/1"]["mtu"] == 1500
    assert node.verify(change) is True

    # Rollback
    rollback_res = node.rollback(snapshot_id)
    assert rollback_res["rolled_back"] is True
    assert node.interfaces["ge-0/0/1"]["mtu"] == 9000


def test_simulator_adapter_wrapper() -> None:
    """Verify SimulatorAdapter delegates correctly to MockCMGNode."""
    node = MockCMGNode()
    adapter = SimulatorAdapter(node)

    assert "CMG-02" in adapter.show("show router bgp summary")
    dry_res = adapter.dry_run({"type": "save_config"})
    assert dry_res["valid"] is True
