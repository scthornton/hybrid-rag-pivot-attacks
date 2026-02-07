"""Tests for pipeline implementations."""

import pytest


class TestVectorOnlyPipeline:
    @pytest.mark.integration
    def test_placeholder(self):
        pytest.skip("Requires ChromaDB + populated index")


class TestHybridPipeline:
    @pytest.mark.integration
    def test_placeholder(self):
        pytest.skip("Requires ChromaDB + Neo4j + populated indexes")
