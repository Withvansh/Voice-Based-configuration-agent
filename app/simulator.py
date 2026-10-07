"""In-memory simulation of CMG node CMG-02."""

import copy
import uuid
from typing import Any, Dict, List, Optional


class MockCMGNode:
    """In-memory simulated CMG-02 network node."""

    def __init__(self, node_name: str = "CMG-02") -> None:
        """Initialize CMG node with fictional state."""
        self.node_name: str = node_name
        self.interfaces: Dict[str, Dict[str, Any]] = {
            "ge-0/0/1": {"admin": "up", "oper": "up", "mtu": 9000, "ip": "10.0.0.1/24"},
            "ge-0/0/2": {"admin": "up", "oper": "up", "mtu": 1500, "ip": "10.0.0.2/24"},
            "ge-0/0/3": {"admin": "up", "oper": "up", "mtu": 1500, "ip": "10.0.0.3/24"},
            "mgmt0": {"admin": "up", "oper": "up", "mtu": 1500, "ip": "10.0.0.254/24"},
        }
        self.bgp_peers: List[Dict[str, Any]] = [
            {"peer_ip": "10.0.0.10", "asn": 65001, "state": "Established"},
            {"peer_ip": "10.0.0.20", "asn": 65002, "state": "Established"},
            {"peer_ip": "10.0.0.30", "asn": 65003, "state": "Active"},
        ]
        self.snapshots: Dict[str, Dict[str, Any]] = {}
        self.config_saved: bool = True
        self.force_verify_failure: bool = False

    def show(self, command: str) -> str:
        """Return simulated command output formatted as text tables."""
        cmd_clean = " ".join(command.strip().lower().split())

        # Normalize router bgp summary commands (e.g., 'show router bgp summary' or 'show router 100 bgp summary')
        if "show router" in cmd_clean and "bgp summary" in cmd_clean:
            established_count = sum(1 for p in self.bgp_peers if p["state"].lower() == "established")
            lines = [
                "=" * 79,
                f"BGP Router Summary for Node: {self.node_name}",
                "=" * 79,
                f"BGP Admin State : Up                   BGP Oper State : Up",
                f"Total Peers     : {len(self.bgp_peers)}                    Peers Up       : {established_count}",
                "-" * 79,
                f"{'Peer IP':<16} {'AS':<8} {'State':<15} {'Up/Down':<14} {'Rcvd':<8} {'Sent':<8}",
                "-" * 79,
            ]
            for peer in self.bgp_peers:
                state_str = peer["state"]
                updown = "04d 12h 21m" if state_str == "Established" else "00d 00h 42m"
                rcvd = "1420" if state_str == "Established" else "0"
                sent = "890" if state_str == "Established" else "0"
                lines.append(f"{peer['peer_ip']:<16} {peer['asn']:<8} {state_str:<15} {updown:<14} {rcvd:<8} {sent:<8}")
            lines.append("=" * 79)
            return "\n".join(lines)

        if cmd_clean == "show router interface":
            lines = [
                "=" * 79,
                f"Interface Table (Router: Base) - Node: {self.node_name}",
                "=" * 79,
                f"{'Interface-Name':<22} {'Adm':<7} {'Opr':<7} {'MTU':<7} {'IP-Address'}",
                "-" * 79,
            ]
            for name, data in self.interfaces.items():
                adm = data["admin"].capitalize()
                opr = data["oper"].capitalize()
                mtu = str(data["mtu"])
                ip = data["ip"]
                lines.append(f"{name:<22} {adm:<7} {opr:<7} {mtu:<7} {ip}")
            lines.append("=" * 79)
            return "\n".join(lines)

        if cmd_clean == "show system alarm":
            lines = [
                "=" * 79,
                f"Active System Alarms - Node: {self.node_name}",
                "=" * 79,
                f"{'Severity':<12} {'Alarm ID':<10} {'Description'}",
                "-" * 79,
                f"{'Major':<12} {'ALM-104':<10} {'BGP session down: Peer 10.0.0.30 (AS 65003)'}",
                f"{'Minor':<12} {'ALM-058':<10} {'High memory utilization threshold warning (78%)'}",
                "=" * 79,
            ]
            return "\n".join(lines)

        if cmd_clean == "show system ntp":
            lines = [
                "=" * 79,
                f"NTP Status - Node: {self.node_name}",
                "=" * 79,
                "Configured      : Yes                  Stratum         : 2",
                "Admin Status    : Up                   Oper Status     : Synchronized",
                "Reference Clock : 10.0.0.100           Jitter          : 0.124 ms",
                "Offset          : +0.035 ms            Last Sync       : 12 seconds ago",
                "=" * 79,
            ]
            return "\n".join(lines)

        if cmd_clean == "show mobile-gateway pdn statistics summary":
            lines = [
                "=" * 79,
                f"Mobile Gateway PDN Statistics Summary - Node: {self.node_name}",
                "=" * 79,
                "Total PDN Sessions     : 245000",
                "Active Bearers         : 312000",
                "Dedicated Bearers      : 67000",
                "SGW Sessions           : 122500",
                "PGW Sessions           : 122500",
                "Session Setup Success  : 99.98%",
                "=" * 79,
            ]
            return "\n".join(lines)

        if "show mobile-gateway pdn apn" in cmd_clean and "statistics" in cmd_clean:
            lines = [
                "=" * 79,
                f"Mobile Gateway APN Statistics: ims - Node: {self.node_name}",
                "=" * 79,
                "Active IMS Sessions    : 95000",
                "IMS Bearer Drops       : 0",
                "VoLTE Traffic Volume   : 1.45 Gbps",
                "=" * 79,
            ]
            return "\n".join(lines)

        return f"Error: command not supported by simulator: '{command}'"

    def dry_run(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Validate proposed change and return diff without modifying state."""
        change_type = change.get("type")
        errors: List[str] = []
        diff: str = ""

        if change_type == "set_mtu":
            iface = change.get("interface")
            val = change.get("value")
            if not iface or iface not in self.interfaces:
                errors.append(f"Interface '{iface}' not found on node {self.node_name}")
            if val is None:
                errors.append("MTU value must be provided")
            elif not isinstance(val, int) or not (576 <= val <= 9216):
                errors.append(f"Invalid MTU {val}: must be between 576 and 9216")

            if not errors and iface:
                current_mtu = self.interfaces[iface]["mtu"]
                diff = f"- mtu {current_mtu}\n+ mtu {val}"

        elif change_type == "interface_admin":
            iface = change.get("interface")
            state = change.get("state")
            if not iface or iface not in self.interfaces:
                errors.append(f"Interface '{iface}' not found on node {self.node_name}")

            norm_state = ""
            if state in ["down", "shutdown"]:
                norm_state = "down"
            elif state in ["up", "no shutdown", "no_shutdown"]:
                norm_state = "up"
            else:
                errors.append(f"Invalid admin state '{state}': must be 'shutdown'/'down' or 'no shutdown'/'up'")

            if not errors and iface:
                current_state = self.interfaces[iface]["admin"]
                diff = f"- admin-state {current_state}\n+ admin-state {norm_state}"

        elif change_type == "save_config":
            diff = "Configuration will be saved to persistent storage."

        else:
            errors.append(f"Unsupported change type: '{change_type}'")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "diff": diff,
        }

    def apply(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Take a snapshot, apply valid configuration change, and return result."""
        val_result = self.dry_run(change)
        if not val_result["valid"]:
            return {"applied": False, "errors": val_result["errors"]}

        # Create snapshot before mutation
        snapshot_id = f"snap_{uuid.uuid4().hex[:8]}"
        self.snapshots[snapshot_id] = {
            "interfaces": copy.deepcopy(self.interfaces),
            "bgp_peers": copy.deepcopy(self.bgp_peers),
            "config_saved": self.config_saved,
        }

        change_type = change.get("type")
        if change_type == "set_mtu":
            iface = change["interface"]
            self.interfaces[iface]["mtu"] = change["value"]
            self.config_saved = False

        elif change_type == "interface_admin":
            iface = change["interface"]
            state = change["state"]
            target = "down" if state in ["down", "shutdown"] else "up"
            self.interfaces[iface]["admin"] = target
            self.interfaces[iface]["oper"] = target
            self.config_saved = False

        elif change_type == "save_config":
            self.config_saved = True

        return {"applied": True, "snapshot_id": snapshot_id}

    def rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """Restore node state from saved snapshot."""
        if snapshot_id not in self.snapshots:
            return {
                "rolled_back": False,
                "snapshot_id": snapshot_id,
                "message": f"Snapshot '{snapshot_id}' not found",
            }

        saved_state = self.snapshots[snapshot_id]
        self.interfaces = copy.deepcopy(saved_state["interfaces"])
        self.bgp_peers = copy.deepcopy(saved_state["bgp_peers"])
        self.config_saved = saved_state["config_saved"]
        return {
            "rolled_back": True,
            "snapshot_id": snapshot_id,
            "message": f"Successfully restored snapshot {snapshot_id}",
        }

    def verify(self, change: Dict[str, Any]) -> bool:
        """Verify that current node state matches the requested change."""
        if self.force_verify_failure:
            return False

        change_type = change.get("type")
        if change_type == "set_mtu":
            iface = change.get("interface")
            val = change.get("value")
            return bool(iface in self.interfaces and self.interfaces[iface]["mtu"] == val)

        if change_type == "interface_admin":
            iface = change.get("interface")
            state = change.get("state")
            expected = "down" if state in ["down", "shutdown"] else "up"
            return bool(iface in self.interfaces and self.interfaces[iface]["admin"] == expected)

        if change_type == "save_config":
            return self.config_saved

        return False
