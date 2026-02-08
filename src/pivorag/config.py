"""Configuration management for PivoRAG experiments.

Loads pipeline and dataset configs from YAML, with environment
variable overrides for secrets (Neo4j credentials, API keys).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class SensitivityTier(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"

    @property
    def level(self) -> int:
        return {
            self.PUBLIC: 0,
            self.INTERNAL: 1,
            self.CONFIDENTIAL: 2,
            self.RESTRICTED: 3,
        }[self]

    def __ge__(self, other: SensitivityTier) -> bool:
        return self.level >= other.level

    def __gt__(self, other: SensitivityTier) -> bool:
        return self.level > other.level

    def __le__(self, other: SensitivityTier) -> bool:
        return self.level <= other.level

    def __lt__(self, other: SensitivityTier) -> bool:
        return self.level < other.level


class VectorConfig(BaseModel):
    enabled: bool = True
    model: str = "all-MiniLM-L6-v2"
    top_k: int = 10
    similarity_threshold: float = 0.3
    auth_prefilter: bool = True


class GraphConfig(BaseModel):
    enabled: bool = True
    max_hops: int = 2
    max_branching_factor: int = 10
    max_total_nodes: int = 50
    expansion_algo: str = "bfs"
    edge_types: list[str] = Field(default_factory=lambda: [
        "CONTAINS", "MENTIONS", "BELONGS_TO",
        "DEPENDS_ON", "OWNED_BY", "DERIVED_FROM",
    ])


class DefenseConfig(BaseModel):
    per_hop_authz: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    edge_allowlist: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    budgets: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    trust_weighting: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    merge_filter: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})


class PipelineConfig(BaseModel):
    name: str
    variant: str
    vector: VectorConfig = Field(default_factory=VectorConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    defenses: DefenseConfig = Field(default_factory=DefenseConfig)


class EnvSettings(BaseSettings):
    """Environment-based settings for secrets and connection strings."""

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    embedding_model: str = "all-MiniLM-L6-v2"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def load_pipeline_config(config_path: str | Path) -> PipelineConfig:
    """Load a pipeline configuration from a YAML file."""
    path = Path(config_path)
    with path.open() as f:
        raw = yaml.safe_load(f)

    pipeline_data = raw.get("pipeline", {})
    pipeline_data["vector"] = raw.get("vector", {})
    pipeline_data["graph"] = raw.get("graph", {})
    pipeline_data["defenses"] = raw.get("defenses", {})
    return PipelineConfig(**pipeline_data)


def load_yaml(config_path: str | Path) -> dict[str, Any]:
    """Load any YAML config file as a dictionary."""
    with Path(config_path).open() as f:
        return yaml.safe_load(f)
