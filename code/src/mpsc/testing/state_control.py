"""State control module for MPSC - implements state isolation strategies"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StateControl(ABC):
    """Abstract base class for state control strategies"""

    @abstractmethod
    def snapshot(self) -> str:
        """Take a snapshot and return snapshot ID"""
        ...

    @abstractmethod
    def revert(self, snapshot_id: str) -> None:
        """Revert to a snapshot"""
        ...

    @abstractmethod
    def fresh_deployment(self) -> None:
        """Reset to fresh state"""
        ...


class SnapshotRevertStateControl(StateControl):
    """State control using blockchain snapshots"""

    def __init__(self, backend) -> None:
        self._backend = backend
        self._snapshots: dict[str, int] = {}
        self._counter = 0

    def snapshot(self) -> str:
        """Take a snapshot using evm_snapshot"""
        self._counter += 1
        snapshot_id = f"snapshot_{self._counter}"

        # Use tester snapshot if available
        if hasattr(self._backend, "_tester"):
            block_number = self._backend._tester.take_snapshot()
            self._snapshots[snapshot_id] = block_number

        return snapshot_id

    def revert(self, snapshot_id: str) -> None:
        """Revert using evm_revert"""
        if snapshot_id not in self._snapshots:
            raise ValueError(f"Unknown snapshot: {snapshot_id}")

        if hasattr(self._backend, "_tester"):
            self._backend._tester.revert_to_snapshot(self._snapshots[snapshot_id])

    def fresh_deployment(self) -> None:
        """Reset the entire chain"""
        if hasattr(self._backend, "reset"):
            self._backend.reset()


class FreshDeploymentStateControl(StateControl):
    """State control by re-deploying contract for each test"""

    def __init__(self, backend_factory) -> None:
        self._backend_factory = backend_factory
        self._backend = None

    def snapshot(self) -> str:
        """Create fresh backend"""
        self._backend = self._backend_factory()
        return "fresh"

    def revert(self, snapshot_id: str) -> None:
        """Create fresh backend again"""
        self._backend = self._backend_factory()

    def fresh_deployment(self) -> None:
        """Create fresh backend"""
        self._backend = self._backend_factory()

    @property
    def backend(self):
        return self._backend
