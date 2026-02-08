"""Tests for dataset adapter interface compliance and concrete implementations."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pivorag.config import SensitivityTier
from pivorag.datasets.base import DatasetAdapter
from pivorag.datasets.enron import (
    EnronEmailAdapter,
    classify_sensitivity,
    infer_tenant,
    parse_email_row,
)
from pivorag.datasets.sec_edgar import (
    COMPANIES,
    SECTION_SENSITIVITY,
    SECEdgarAdapter,
    _extract_10k_sections,
)
from pivorag.graph.schema import Document

# ---------------------------------------------------------------------------
# Interface compliance — all adapters must satisfy the DatasetAdapter contract
# ---------------------------------------------------------------------------


class TestDatasetAdapterInterface:
    """Verify that each adapter implements all abstract methods."""

    def _check_adapter(self, adapter: DatasetAdapter) -> None:
        assert isinstance(adapter.name, str)
        assert len(adapter.name) > 0

        tenants = adapter.get_tenants()
        assert isinstance(tenants, list)
        assert len(tenants) >= 2

        dist = adapter.get_sensitivity_distribution()
        assert isinstance(dist, dict)
        assert all(isinstance(k, SensitivityTier) for k in dist)
        assert abs(sum(dist.values()) - 1.0) < 0.05

        bridges = adapter.get_bridge_entities()
        assert isinstance(bridges, list)
        for b in bridges:
            assert "name" in b
            assert "type" in b
            assert "connects" in b

        collection = adapter.get_collection_name()
        assert adapter.name in collection

    def test_enron_interface(self, tmp_path: Path) -> None:
        adapter = EnronEmailAdapter(data_dir=tmp_path)
        self._check_adapter(adapter)

    def test_edgar_interface(self, tmp_path: Path) -> None:
        adapter = SECEdgarAdapter(data_dir=tmp_path)
        self._check_adapter(adapter)


# ---------------------------------------------------------------------------
# Enron adapter tests
# ---------------------------------------------------------------------------


SAMPLE_EMAIL_RFC2822 = (
    "Message-ID: <test@enron.com>\n"
    "Date: Mon, 1 Jan 2001 12:00:00 -0600\n"
    "From: lay-k@enron.com\n"
    "To: skilling-j@enron.com\n"
    "Subject: Strategic Plan Discussion\n"
    "\n"
    "Jeff,\n\n"
    "Please review the attached strategic plan for the board meeting.\n"
    "This is privileged and confidential information.\n\n"
    "Regards,\nKen Lay\n"
)


class TestEnronSensitivity:
    def test_restricted_attorney_privilege(self) -> None:
        result = classify_sensitivity("Legal Update", "attorney-client privilege applies")
        assert result == "RESTRICTED"

    def test_restricted_password(self) -> None:
        assert classify_sensitivity("", "password: secretpass123") == "RESTRICTED"

    def test_confidential_deal_terms(self) -> None:
        result = classify_sensitivity("Deal Review", "The deal terms include a 10% premium")
        assert result == "CONFIDENTIAL"

    def test_confidential_compensation(self) -> None:
        result = classify_sensitivity("", "compensation plan review for executive team")
        assert result == "CONFIDENTIAL"

    def test_internal_memo(self) -> None:
        result = classify_sensitivity("Team Update", "internal memo about project status")
        assert result == "INTERNAL"

    def test_public_default(self) -> None:
        assert classify_sensitivity("Hello", "Just wanted to say hi") == "PUBLIC"


class TestEnronTenantMapping:
    def test_known_executive(self) -> None:
        assert infer_tenant("lay-k@enron.com") == "executive"

    def test_known_trader(self) -> None:
        assert infer_tenant("farmer-d@enron.com") == "trading"

    def test_known_legal(self) -> None:
        assert infer_tenant("taylor-m@enron.com") == "legal"

    def test_known_finance(self) -> None:
        assert infer_tenant("fastow-a@enron.com") == "finance"

    def test_folder_heuristic_trading(self) -> None:
        assert infer_tenant("unknown@enron.com", "allen-p/trading/sent") == "trading"

    def test_folder_heuristic_legal(self) -> None:
        assert infer_tenant("unknown@enron.com", "jones-t/legal/memos") == "legal"

    def test_fallback_deterministic(self) -> None:
        # Unknown sender, no folder hints — should be deterministic
        t1 = infer_tenant("nobody@enron.com")
        t2 = infer_tenant("nobody@enron.com")
        assert t1 == t2

    def test_name_format_handling(self) -> None:
        # Handle "Name <addr>" format
        assert infer_tenant("Ken Lay <lay-k@enron.com>") == "executive"


class TestEnronEmailParsing:
    def test_parse_valid_email(self) -> None:
        row = {"file": "lay-k/inbox/1.", "message": SAMPLE_EMAIL_RFC2822}
        result = parse_email_row(row)
        assert result is not None
        assert result["tenant"] == "executive"
        # "strategic plan" + "privileged and confidential"
        assert result["sensitivity"] == "RESTRICTED"
        assert "Ken Lay" in result["text"]

    def test_parse_empty_message(self) -> None:
        row = {"file": "test", "message": ""}
        assert parse_email_row(row) is None

    def test_parse_short_body(self) -> None:
        row = {"file": "test", "message": "From: a@b.com\nTo: c@d.com\n\nHi"}
        assert parse_email_row(row) is None


class TestEnronDocumentLoading:
    def test_load_from_csv(self, tmp_path: Path) -> None:
        """Write a small CSV and verify the adapter can load it."""
        csv_path = tmp_path / "emails.csv"
        with csv_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "message"])
            writer.writeheader()
            for i in range(10):
                body = (
                    "This is test email with enough text to pass the "
                    f"minimum length filter number {i} for testing.\n"
                )
                msg = (
                    f"Message-ID: <test{i}@enron.com>\n"
                    f"Date: Mon, {i+1} Jan 2001 12:00:00 -0600\n"
                    f"From: lay-k@enron.com\n"
                    f"To: skilling-j@enron.com\n"
                    f"Subject: Test email {i}\n"
                    f"\n"
                    f"{body}"
                )
                writer.writerow({"file": f"lay-k/inbox/{i}.", "message": msg})

        adapter = EnronEmailAdapter(data_dir=tmp_path, max_emails=10)
        docs = adapter.load_documents()
        assert len(docs) > 0
        assert all(isinstance(d, Document) for d in docs)
        assert all(d.tenant in adapter.get_tenants() for d in docs)

    def test_load_missing_csv(self, tmp_path: Path) -> None:
        adapter = EnronEmailAdapter(data_dir=tmp_path)
        with pytest.raises(FileNotFoundError, match="emails.csv"):
            adapter.load_documents()


class TestEnronQueryGeneration:
    def test_generates_correct_counts(self, tmp_path: Path) -> None:
        adapter = EnronEmailAdapter(data_dir=tmp_path)
        queries = adapter.generate_queries(n_benign=50, n_adversarial=30)
        benign = [q for q in queries if q.query_type == "benign"]
        adversarial = [q for q in queries if q.query_type == "adversarial"]
        assert len(benign) == 50
        assert len(adversarial) == 30

    def test_queries_have_valid_tenants(self, tmp_path: Path) -> None:
        adapter = EnronEmailAdapter(data_dir=tmp_path)
        queries = adapter.generate_queries(n_benign=20, n_adversarial=20)
        valid_tenants = set(adapter.get_tenants())
        for q in queries:
            assert q.user_tenant in valid_tenants

    def test_reproducible(self, tmp_path: Path) -> None:
        a1 = EnronEmailAdapter(data_dir=tmp_path, seed=42)
        a2 = EnronEmailAdapter(data_dir=tmp_path, seed=42)
        q1 = a1.generate_queries(n_benign=10, n_adversarial=10)
        q2 = a2.generate_queries(n_benign=10, n_adversarial=10)
        assert [q.query for q in q1] == [q.query for q in q2]


# ---------------------------------------------------------------------------
# EDGAR adapter tests
# ---------------------------------------------------------------------------


class TestEdgar10KParsing:
    def test_extract_sections(self) -> None:
        text = (
            "\nITEM 1. Business Description\n"
            "Apple Inc designs, manufactures, and markets smartphones, "
            "personal computers, tablets, wearables, and accessories. "
            "The company also sells a variety of related services. "
            "This is enough text to pass the 100-character minimum.\n"
            "\nITEM 1A. Risk Factors\n"
            "The Company faces significant competition in all markets. "
            "These risk factors include supply chain disruptions, "
            "regulatory changes, and competitive pressure in key segments. "
            "The technology industry is subject to rapid change.\n"
            "\nITEM 7. Management's Discussion and Analysis\n"
            "Revenue increased 8% year over year driven by iPhone sales. "
            "Services revenue grew 14% and represents an increasing "
            "share of total revenue. The company continues to invest "
            "heavily in research and development activities.\n"
        )

        sections = _extract_10k_sections(text)
        assert len(sections) == 3
        assert sections[0]["section"] == "item_1"
        assert sections[1]["section"] == "item_1a"
        assert sections[2]["section"] == "item_7"

    def test_skip_short_sections(self) -> None:
        text = (
            "\nITEM 4. Mine Safety Disclosures\n"
            "Not applicable.\n"
            "\nITEM 7. MD&A Analysis of Financial Condition\n"
            "The company's financial condition improved significantly "
            "during the fiscal year. Revenue grew across all segments "
            "with particularly strong performance in the services business. "
            "Operating margins expanded due to favorable product mix.\n"
        )
        sections = _extract_10k_sections(text)
        # Item 4 should be skipped (body < 100 chars)
        assert all(s["section"] != "item_4" for s in sections)


class TestEdgarSensitivityMapping:
    def test_public_sections(self) -> None:
        for item in ["item_1", "item_2", "item_3"]:
            assert SECTION_SENSITIVITY[item] == "PUBLIC"

    def test_restricted_sections(self) -> None:
        assert SECTION_SENSITIVITY["item_5"] == "RESTRICTED"
        assert SECTION_SENSITIVITY["item_13"] == "RESTRICTED"

    def test_confidential_sections(self) -> None:
        assert SECTION_SENSITIVITY["item_11"] == "CONFIDENTIAL"
        assert SECTION_SENSITIVITY["item_12"] == "CONFIDENTIAL"


class TestEdgarDocumentLoading:
    def test_load_from_cache(self, tmp_path: Path) -> None:
        """Create a cached filing and verify the adapter loads it."""
        company = COMPANIES[0]  # Apple
        cache_file = tmp_path / f"{company['ticker']}_10k.json"
        filing_data = [{
            "accession": "0000320193-23-000106",
            "url": "https://example.com/filing.htm",
            "sections": [
                {
                    "section": "item_1",
                    "title": "Business Description",
                    "text": "Apple designs and sells consumer electronics. " * 20,
                },
                {
                    "section": "item_11",
                    "title": "Executive Compensation",
                    "text": "CEO compensation package includes base salary. " * 20,
                },
            ],
        }]
        cache_file.write_text(json.dumps(filing_data))

        adapter = SECEdgarAdapter(
            data_dir=tmp_path,
            companies=[company],
            use_cache=True,
        )
        docs = adapter.load_documents()
        assert len(docs) == 2
        assert docs[0].tenant == "tech"
        assert docs[0].sensitivity == "PUBLIC"   # item_1
        assert docs[1].sensitivity == "CONFIDENTIAL"  # item_11

    def test_no_filings_returns_empty(self, tmp_path: Path) -> None:
        company = {
            "cik": "0000000001", "name": "Test Corp",
            "ticker": "TST", "sector": "tech",
        }
        cache_file = tmp_path / "TST_10k.json"
        cache_file.write_text("[]")

        adapter = SECEdgarAdapter(data_dir=tmp_path, companies=[company])
        docs = adapter.load_documents()
        assert len(docs) == 0


class TestEdgarQueryGeneration:
    def test_generates_correct_counts(self, tmp_path: Path) -> None:
        adapter = SECEdgarAdapter(data_dir=tmp_path)
        queries = adapter.generate_queries(n_benign=40, n_adversarial=20)
        benign = [q for q in queries if q.query_type == "benign"]
        adversarial = [q for q in queries if q.query_type == "adversarial"]
        assert len(benign) == 40
        assert len(adversarial) == 20

    def test_queries_have_valid_tenants(self, tmp_path: Path) -> None:
        adapter = SECEdgarAdapter(data_dir=tmp_path)
        queries = adapter.generate_queries(n_benign=20, n_adversarial=20)
        valid_tenants = set(adapter.get_tenants())
        for q in queries:
            assert q.user_tenant in valid_tenants

    def test_reproducible(self, tmp_path: Path) -> None:
        a1 = SECEdgarAdapter(data_dir=tmp_path, seed=42)
        a2 = SECEdgarAdapter(data_dir=tmp_path, seed=42)
        q1 = a1.generate_queries(n_benign=10, n_adversarial=10)
        q2 = a2.generate_queries(n_benign=10, n_adversarial=10)
        assert [q.query for q in q1] == [q.query for q in q2]


# ---------------------------------------------------------------------------
# DatasetStats tests
# ---------------------------------------------------------------------------


class TestDatasetStats:
    def test_stats_from_documents(self, tmp_path: Path) -> None:
        adapter = EnronEmailAdapter(data_dir=tmp_path)
        docs = [
            Document(
                doc_id="d1", title="t1", text="x" * 100,
                tenant="trading", sensitivity="PUBLIC",
            ),
            Document(
                doc_id="d2", title="t2", text="y" * 100,
                tenant="legal", sensitivity="RESTRICTED",
            ),
            Document(
                doc_id="d3", title="t3", text="z" * 100,
                tenant="trading", sensitivity="PUBLIC",
            ),
        ]
        stats = adapter.get_stats(docs)
        assert stats.total_documents == 3
        assert "trading" in stats.tenants
        assert "legal" in stats.tenants
        assert stats.bridge_entity_count > 0
