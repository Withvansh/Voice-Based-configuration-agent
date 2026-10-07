"""Dialogue state machine, intent parsing, and configuration guardrails."""

import os
import re
from typing import Any, Dict, List, Optional, Tuple
from app.audit import log_audit
from app.device_adapter import DeviceAdapter
from app.rag import CommandRAG


BLOCKLIST_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "blocklist.txt")
)


def load_blocklist() -> List[str]:
    """Load blocked command terms from disk."""
    items = ["admin reboot now", "admin reboot", "format", "rm -rf", "factory-default"]
    if os.path.exists(BLOCKLIST_PATH):
        with open(BLOCKLIST_PATH, "r", encoding="utf-8") as f:
            file_items = [line.strip().lower() for line in f if line.strip()]
            if file_items:
                return file_items
    return items


def is_blocked(text: str, blocklist: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Check if input text violates the safety blocklist."""
    items = blocklist or load_blocklist()
    cleaned = text.strip().lower()

    # Direct match or containment
    for item in items:
        if item in cleaned:
            return True, item

    # Check standalone dangerous keywords
    dangerous_keywords = ["reboot", "rm -rf", "format", "factory-default"]
    for kw in dangerous_keywords:
        if re.search(rf"\b{re.escape(kw)}\b", cleaned):
            return True, kw

    return False, ""


def parse_intent(text: str) -> Dict[str, Any]:
    """Extract dialogue intent and slots using rule-based heuristics."""
    cleaned = text.strip()
    lower = cleaned.lower()

    # 1. Check Confirmation / Cancellation
    if lower in ["confirm", "yes confirm", "proceed"]:
        return {"intent": "confirm", "slots": {}}
    if lower in ["cancel", "abort", "no cancel"]:
        return {"intent": "cancel", "slots": {}}

    # 2. Extract interface if present (e.g., ge-0/0/1, mgmt0)
    interface = None
    iface_match = re.search(r"\b(ge-\d+/\d+/\d+|mgmt\d+)\b", cleaned, re.IGNORECASE)
    if iface_match:
        interface = iface_match.group(1).lower()

    # 3. Extract node if specified (excluding interface strings so ge-0 is not matched as node)
    node = None
    text_for_node = re.sub(r"\b(ge-\d+/\d+/\d+|mgmt\d+)\b", "", cleaned, flags=re.IGNORECASE)
    node_match = re.search(r"\b(cmg-[0-9a-zA-Z]+|[a-zA-Z]+-[0-9]+)\b", text_for_node, re.IGNORECASE)
    if node_match:
        node = node_match.group(1).upper()

    # 4. Extract MTU value
    mtu_val = None
    mtu_match = re.search(r"\bmtu\s*(\d+)\b", cleaned, re.IGNORECASE)
    if mtu_match:
        mtu_val = int(mtu_match.group(1))
    else:
        # Fallback to standalone 3-4 digit numbers if MTU keyword present
        if "mtu" in lower:
            digits = re.findall(r"\b(\d{3,5})\b", cleaned)
            if digits:
                mtu_val = int(digits[0])

    # Config Intents
    if "set mtu" in lower or "configure mtu" in lower or "change mtu" in lower:
        slots: Dict[str, Any] = {}
        if node:
            slots["node"] = node
        if interface:
            slots["interface"] = interface
        if mtu_val:
            slots["value"] = mtu_val
        return {"intent": "set_mtu", "slots": slots}

    if "no shutdown" in lower or "bring up" in lower or "enable port" in lower or "no shut" in lower:
        slots = {}
        if node:
            slots["node"] = node
        if interface:
            slots["interface"] = interface
        slots["state"] = "up"
        return {"intent": "interface_no_shutdown", "slots": slots}

    if "shut down" in lower or "shutdown" in lower or "disable port" in lower or "disable interface" in lower:
        slots = {}
        if node:
            slots["node"] = node
        if interface:
            slots["interface"] = interface
        slots["state"] = "down"
        return {"intent": "interface_admin", "slots": slots}

    if "save" in lower and ("config" in lower or "configuration" in lower or "admin" in lower):
        slots = {}
        if node:
            slots["node"] = node
        return {"intent": "save_config", "slots": slots}

    # If slot-filling answer was given (e.g. "interface ge-0/0/1 mtu 1500", "ge-0/0/1", "1500")
    if (interface and mtu_val) or ((interface or mtu_val) and "show" not in lower):
        slots = {}
        if interface:
            slots["interface"] = interface
        if mtu_val:
            slots["value"] = mtu_val
        if node:
            slots["node"] = node
        return {"intent": "fill_slots", "slots": slots}

    # Show Intents
    if "bgp" in lower:
        return {"intent": "show_bgp", "slots": {"node": node or "CMG-02"}}
    if "alarm" in lower or "alarms" in lower:
        return {"intent": "show_alarms", "slots": {"node": node or "CMG-02"}}
    if "ntp" in lower or "clock" in lower or "time sync" in lower:
        return {"intent": "show_ntp", "slots": {"node": node or "CMG-02"}}
    if "pdn" in lower or "subscriber" in lower or "apn" in lower or "mobile-gateway" in lower:
        return {"intent": "show_subscribers", "slots": {"node": node or "CMG-02"}}
    if "interface" in lower or "interfaces" in lower:
        return {"intent": "show_interfaces", "slots": {"node": node or "CMG-02"}}

    return {"intent": "unknown", "slots": {"node": node} if node else {}}


class DialogueAgent:
    """Manages multi-turn dialogue state machine and command execution."""

    def __init__(self, adapter: DeviceAdapter, rag: CommandRAG) -> None:
        """Initialize agent with device adapter and RAG index."""
        self.adapter = adapter
        self.rag = rag
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Fetch or initialize session state."""
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "state": "IDLE",
                "pending_intent": None,
                "slots": {},
                "pending_change": None,
                "pending_plan": None,
                "pending_source": None,
            }
        return self.sessions[session_id]

    def reset_session(self, session_id: str) -> None:
        """Reset session to IDLE state."""
        self.sessions[session_id] = {
            "state": "IDLE",
            "pending_intent": None,
            "slots": {},
            "pending_change": None,
            "pending_plan": None,
            "pending_source": None,
        }

    def process(self, session_id: str, text: str) -> Dict[str, Any]:
        """Process user input through dialogue state machine with guardrails."""
        session = self.get_session(session_id)
        current_state = session["state"]

        # Guardrail 1: Blocklist check
        blocked, term = is_blocked(text)
        if blocked:
            log_audit(session_id, "block", {"input": text, "matched_term": term})
            return {
                "session_id": session_id,
                "state": current_state,
                "reply_text": f"Action blocked by safety policy: command or term '{term}' is on the blocklist.",
            }

        # Guardrail 2: Multi-command prevention
        if " and " in text.lower() and ("set " in text.lower() or "shut" in text.lower()):
            log_audit(session_id, "block", {"input": text, "reason": "multiple_commands"})
            return {
                "session_id": session_id,
                "state": current_state,
                "reply_text": "Only one configuration change per request is permitted.",
            }

        parsed = parse_intent(text)
        log_audit(session_id, "intent_parsed", {"input": text, "parsed": parsed})

        # Guardrail 3: Unknown node rejection
        specified_node = parsed["slots"].get("node")
        if specified_node and specified_node != "CMG-02":
            log_audit(session_id, "block", {"input": text, "unknown_node": specified_node})
            return {
                "session_id": session_id,
                "state": "IDLE",
                "reply_text": f"Error: Unknown node '{specified_node}'. Only node CMG-02 is supported.",
            }

        intent = parsed["intent"]

        # Handling AWAITING_CONFIRM state
        if current_state == "AWAITING_CONFIRM":
            if intent == "confirm":
                log_audit(session_id, "confirm", {"phrase": text})
                change = session["pending_change"]
                apply_res = self.adapter.apply(change)
                log_audit(session_id, "apply", apply_res)

                if not apply_res.get("applied"):
                    self.reset_session(session_id)
                    return {
                        "session_id": session_id,
                        "state": "IDLE",
                        "reply_text": f"Apply failed: {apply_res.get('errors')}",
                    }

                snapshot_id = apply_res["snapshot_id"]
                verified = self.adapter.verify(change)
                log_audit(session_id, "verify", {"verified": verified, "change": change})

                if not verified:
                    rollback_res = self.adapter.rollback(snapshot_id)
                    log_audit(session_id, "rollback", rollback_res)
                    self.reset_session(session_id)
                    return {
                        "session_id": session_id,
                        "state": "DONE",
                        "reply_text": (
                            f"Verification failed after applying change. "
                            f"Automatically rolled back to snapshot {snapshot_id}."
                        ),
                    }

                self.reset_session(session_id)
                return {
                    "session_id": session_id,
                    "state": "DONE",
                    "reply_text": (
                        f"Configuration applied and verified successfully on CMG-02. "
                        f"Snapshot ID: {snapshot_id}."
                    ),
                }

            if intent == "cancel":
                log_audit(session_id, "cancel", {"session_id": session_id})
                self.reset_session(session_id)
                return {
                    "session_id": session_id,
                    "state": "IDLE",
                    "reply_text": "Configuration change cancelled. No changes were made.",
                }

            return {
                "session_id": session_id,
                "state": "AWAITING_CONFIRM",
                "reply_text": "A configuration change is pending. Please say 'confirm' to execute or 'cancel' to abort.",
                "plan": session.get("pending_plan"),
                "source": session.get("pending_source"),
            }

        # Handle Show Intents (Read-Only)
        if intent.startswith("show_"):
            show_query_map = {
                "show_bgp": "To check BGP status, they must be UP and connected",
                "show_interfaces": "Verify router interfaces and operational state",
                "show_alarms": "Check active system alarms",
                "show_ntp": "Check system NTP synchronization status",
                "show_subscribers": "Mobile Gateway PDN session and statistics summary",
            }
            query = show_query_map.get(intent, text)
            matches = self.rag.search(query, k=1)
            log_audit(session_id, "rag_lookup", {"query": query, "matches": matches})

            if not matches:
                return {
                    "session_id": session_id,
                    "state": "IDLE",
                    "reply_text": "Command not found in authorized library.",
                }

            match = matches[0]
            cmd = match["command"]
            source = f"{match['source_file']} -> {match['section_heading']}"
            output = self.adapter.show(cmd)

            return {
                "session_id": session_id,
                "state": "IDLE",
                "reply_text": f"Source: {source}\n\n{output}",
                "source": source,
            }

        # Handle Configuration Intents
        config_intents = ["set_mtu", "interface_admin", "interface_no_shutdown", "save_config"]
        if intent in config_intents or current_state == "NEED_DETAILS":
            # If filling slots for a previous intent
            if current_state == "NEED_DETAILS":
                active_intent = session.get("pending_intent")
                session["slots"].update(parsed["slots"])
            elif intent in config_intents:
                active_intent = intent
                session["pending_intent"] = intent
                session["slots"] = parsed["slots"]
            else:
                active_intent = session.get("pending_intent")

            # Check required slots
            missing: List[str] = []
            slots = session["slots"]

            if active_intent == "set_mtu":
                if not slots.get("interface"):
                    missing.append("interface")
                if not slots.get("value"):
                    missing.append("value")

            elif active_intent in ["interface_admin", "interface_no_shutdown"]:
                if not slots.get("interface"):
                    missing.append("interface")

            if missing:
                session["state"] = "NEED_DETAILS"
                if "interface" in missing and "value" in missing:
                    prompt = "Please specify the interface name (e.g. ge-0/0/1) and the MTU value."
                elif "interface" in missing:
                    prompt = "Please specify the interface name (e.g. ge-0/0/1)."
                else:
                    prompt = "Please specify the MTU value."

                return {
                    "session_id": session_id,
                    "state": "NEED_DETAILS",
                    "reply_text": prompt,
                    "needs": missing,
                }

            # All required slots present -> Prepare Plan & Dry-Run
            template_query_map = {
                "set_mtu": "Set MTU on an interface",
                "interface_admin": "Shut down a port",
                "interface_no_shutdown": "Bring up a port",
                "save_config": "Save configuration",
            }
            query = template_query_map.get(active_intent, "")
            matches = self.rag.search(query, k=1)
            log_audit(session_id, "rag_lookup", {"query": query, "matches": matches})

            if not matches:
                self.reset_session(session_id)
                return {
                    "session_id": session_id,
                    "state": "IDLE",
                    "reply_text": "Configuration template not found in authorized library.",
                }

            match = matches[0]
            source = f"{match['source_file']} -> {match['section_heading']}"

            # Construct change payload
            if active_intent == "set_mtu":
                change = {
                    "type": "set_mtu",
                    "interface": slots["interface"],
                    "value": slots["value"],
                    "node": "CMG-02",
                }
            elif active_intent in ["interface_admin", "interface_no_shutdown"]:
                state_val = slots.get("state", "down" if active_intent == "interface_admin" else "up")
                change = {
                    "type": "interface_admin",
                    "interface": slots["interface"],
                    "state": state_val,
                    "node": "CMG-02",
                }
            else:
                change = {"type": "save_config", "node": "CMG-02"}

            # Run dry-run
            dry_run_res = self.adapter.dry_run(change)
            log_audit(session_id, "dry_run", {"change": change, "result": dry_run_res})

            if not dry_run_res.get("valid"):
                err_msg = ", ".join(dry_run_res.get("errors", ["Invalid configuration"]))
                self.reset_session(session_id)
                return {
                    "session_id": session_id,
                    "state": "IDLE",
                    "reply_text": f"Dry-run validation rejected: {err_msg}",
                }

            # Render command template
            raw_tpl = match["command"]
            rendered_cmd = raw_tpl
            if "{interface}" in rendered_cmd and change.get("interface"):
                rendered_cmd = rendered_cmd.replace("{interface}", change["interface"])
            if "{value}" in rendered_cmd and change.get("value") is not None:
                rendered_cmd = rendered_cmd.replace("{value}", str(change["value"]))

            diff = dry_run_res.get("diff", "")
            action_desc = (
                f"set MTU {change.get('value')} on {change.get('interface')}"
                if active_intent == "set_mtu"
                else f"set admin state to {change.get('state')} on {change.get('interface')}"
                if active_intent in ["interface_admin", "interface_no_shutdown"]
                else "save the running configuration"
            )

            plan_text = f"Command: {rendered_cmd}\nDiff:\n{diff}"
            reply_text = (
                f"Source: {source}\n\n"
                f"I will {action_desc} of CMG-02.\n"
                f"Proposed change: `{rendered_cmd}`\n"
                f"Diff:\n{diff}\n\n"
                f"Say 'confirm' to apply or 'cancel' to abort."
            )

            session["state"] = "AWAITING_CONFIRM"
            session["pending_change"] = change
            session["pending_plan"] = plan_text
            session["pending_source"] = source

            return {
                "session_id": session_id,
                "state": "AWAITING_CONFIRM",
                "reply_text": reply_text,
                "plan": plan_text,
                "source": source,
            }

        # Unknown intent
        return {
            "session_id": session_id,
            "state": "IDLE",
            "reply_text": "Command or intent not recognized. I did not find a matching procedure.",
        }
