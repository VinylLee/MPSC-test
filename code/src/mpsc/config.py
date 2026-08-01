"""Configuration management for MPSC"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class MPSCConfig:
    """Main configuration for MPSC"""

    # Parameters
    tau: float = 0.1  # Detection threshold for K_ik
    tau_c: float | None = None  # Pruning threshold for combined score
    min_set_size: int | None = None  # Minimum MR set size
    candidate_pool_size: int = 10  # ART candidate pool size

    # Weights for CombinedScore
    ms_weight: float = 0.5
    ds_weight: float = 0.5

    # Compiler versions
    compiler_versions: list[str] = field(
        default_factory=lambda: ["0.4.11", "0.4.19", "0.4.24", "0.4.25"]
    )

    # Random seed
    seed: int | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> MPSCConfig:
        """Load configuration from YAML file"""
        with open(path) as f:
            data = yaml.safe_load(f)

        config = cls()

        # Extract parameters from YAML
        if "mr_optimization" in data:
            opt = data["mr_optimization"]
            if opt.get("threshold_tau") is not None:
                config.tau = opt["threshold_tau"]
            if opt.get("pruning_threshold_tau_c") is not None:
                config.tau_c = opt["pruning_threshold_tau_c"]
            if opt.get("min_set_size") is not None:
                config.min_set_size = opt["min_set_size"]
            if "weights" in opt:
                config.ms_weight = opt["weights"].get("mutation_score", 0.5)
                config.ds_weight = opt["weights"].get("difference_score", 0.5)

        if "test_generation" in data:
            tg = data["test_generation"]
            if tg.get("candidate_pool_size") is not None:
                config.candidate_pool_size = tg["candidate_pool_size"]

        if "random" in data and data["random"].get("seed") is not None:
            config.seed = data["random"]["seed"]

        if "compiler" in data and data["compiler"].get("versions"):
            config.compiler_versions = [
                v for v in data["compiler"]["versions"] if v is not None
            ]

        return config


def load_config(path: str | Path | None = None) -> MPSCConfig:
    """Load configuration from file or return default"""
    if path is not None:
        return MPSCConfig.from_yaml(path)
    return MPSCConfig()
