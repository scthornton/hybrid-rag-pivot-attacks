"""Pydantic models for knowledge graph nodes and edges.

Defines the graph schema used throughout the pipeline:
node types (Document, Chunk, Entity, System, Project, User, Source)
and edge types (CONTAINS, MENTIONS, BELONGS_TO, etc.).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EdgeType(StrEnum):
    CONTAINS = "CONTAINS"
    MENTIONS = "MENTIONS"
    BELONGS_TO = "BELONGS_TO"
    DEPENDS_ON = "DEPENDS_ON"
    OWNED_BY = "OWNED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    RELATED_TO = "RELATED_TO"


class Document(BaseModel):
    doc_id: str
    title: str
    text: str = ""
    source: str = ""
    tenant: str = ""
    sensitivity: str = "PUBLIC"
    created_at: datetime = Field(default_factory=datetime.now)
    provenance_score: float = 1.0


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str = ""
    tenant: str = ""
    sensitivity: str = "PUBLIC"
    embedding_ref: str | None = None
    provenance_score: float = 1.0


class Entity(BaseModel):
    entity_id: str
    entity_type: str
    canonical_name: str
    tenant: str = ""
    sensitivity: str | None = None


class System(BaseModel):
    system_id: str
    name: str
    tenant: str = ""
    sensitivity: str = "INTERNAL"


class Project(BaseModel):
    project_id: str
    name: str
    tenant: str = ""
    sensitivity: str = "INTERNAL"


class User(BaseModel):
    user_id: str
    tenant: str
    clearance: str = "PUBLIC"


class Source(BaseModel):
    source_id: str
    name: str
    trust_level: float = 1.0


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict = Field(default_factory=dict)
    trust_score: float = 1.0


class GraphNode(BaseModel):
    """Generic graph node for traversal results."""

    node_id: str
    node_type: str
    tenant: str = ""
    sensitivity: str = "PUBLIC"
    provenance_score: float = 1.0
    properties: dict = Field(default_factory=dict)
