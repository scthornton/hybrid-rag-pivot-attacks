"""Shared test fixtures for pivorag test suite."""

from __future__ import annotations

import pytest

from pivorag.config import PipelineConfig
from pivorag.graph.schema import Chunk, Document, Entity, GraphNode


@pytest.fixture
def sample_document() -> Document:
    return Document(
        doc_id="doc_001",
        title="Project Alpha Architecture",
        text="Project Alpha uses microservices deployed on Kubernetes. "
             "The payment service connects to the billing database.",
        source="engineering_wiki",
        tenant="acme_engineering",
        sensitivity="INTERNAL",
        provenance_score=0.9,
    )


@pytest.fixture
def sample_chunk() -> Chunk:
    return Chunk(
        chunk_id="doc_001_chunk_0000",
        doc_id="doc_001",
        text="Project Alpha uses microservices deployed on Kubernetes.",
        tenant="acme_engineering",
        sensitivity="INTERNAL",
        provenance_score=0.9,
    )


@pytest.fixture
def sample_entities() -> list[Entity]:
    return [
        Entity(
            entity_id="ent_project_alpha_ORG",
            entity_type="ORG",
            canonical_name="project_alpha",
            tenant="acme_engineering",
        ),
        Entity(
            entity_id="ent_kubernetes_TECH",
            entity_type="TECH",
            canonical_name="kubernetes",
            tenant="acme_engineering",
        ),
    ]


@pytest.fixture
def sensitive_node() -> GraphNode:
    """A node the standard user should NOT be able to see."""
    return GraphNode(
        node_id="restricted_creds_001",
        node_type="Credential",
        tenant="umbrella_security",
        sensitivity="RESTRICTED",
        provenance_score=1.0,
    )


@pytest.fixture
def bridge_node() -> GraphNode:
    """A node that bridges two tenants."""
    return GraphNode(
        node_id="shared_vendor_cloudcorp",
        node_type="Entity",
        tenant="",  # Multi-tenant
        sensitivity="INTERNAL",
        provenance_score=0.7,
    )


@pytest.fixture
def sample_pipeline_config() -> PipelineConfig:
    return PipelineConfig(
        name="test_hybrid",
        variant="test",
    )
