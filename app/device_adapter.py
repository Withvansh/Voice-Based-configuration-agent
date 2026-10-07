"""Device adapter abstraction layer and simulator implementation."""

from abc import ABC, abstractmethod
from typing import Any, Dict
from app.simulator import MockCMGNode


class DeviceAdapter(ABC):
    """Abstract base class for device communication adapters."""

    @abstractmethod
    def show(self, command: str) -> str:
        """Execute a read-only show command on the device."""
        pass

    @abstractmethod
    def dry_run(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Validate proposed configuration without altering device state."""
        pass

    @abstractmethod
    def apply(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Apply configuration change to device and take snapshot."""
        pass

    @abstractmethod
    def rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """Roll back device state to previous snapshot."""
        pass

    @abstractmethod
    def verify(self, change: Dict[str, Any]) -> bool:
        """Verify that configuration change took effect."""
        pass


class SimulatorAdapter(DeviceAdapter):
    """Adapter wrapping in-memory MockCMGNode.

    Note: A future RealDeviceAdapter (using Netmiko, Scrapli, or Pexpect over SSH)
    could implement DeviceAdapter to interact with physical network elements.
    """

    def __init__(self, node: MockCMGNode) -> None:
        """Initialize adapter with a simulated CMG node."""
        self.node: MockCMGNode = node

    def show(self, command: str) -> str:
        """Execute show command on mock node."""
        return self.node.show(command)

    def dry_run(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Run dry-run validation on mock node."""
        return self.node.dry_run(change)

    def apply(self, change: Dict[str, Any]) -> Dict[str, Any]:
        """Apply configuration change on mock node."""
        return self.node.apply(change)

    def rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """Roll back configuration on mock node."""
        return self.node.rollback(snapshot_id)

    def verify(self, change: Dict[str, Any]) -> bool:
        """Verify configuration state on mock node."""
        return self.node.verify(change)
