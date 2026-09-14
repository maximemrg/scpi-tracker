"""Tests de l'adaptateur Corum sur fixtures RÉELLES figées (bulletin T2 2026).

Ces tests cassent volontairement si Corum change la structure de sa page
documents ou la mise en page de ses bulletins — c'est leur rôle.
"""

from datetime import date
from pathlib import Path

import pytest

from scpi.models import Confidence, MetricKey, Status
from scpi.pdf import PdfContent
from scpi.registry import ScpiEntry
from scpi.sources import corum
from scpi.sources.corum import TARGET_KEYS, CorumAdapter

FIX = Path(__file__).parent / "fixtures"


def _entry(scpi_id: str) -> ScpiEntry:
    return ScpiEntry(
        scpi_id=scpi_id,
        nom=scpi_id,
        sdg_key="corum_lepargne",
        sdg_nom="Corum L'Épargne",
        domaine="corum.fr",
        fiche_url=f"https://www.corum.fr/nos-scpi/{scpi_id}",
        documents_url=f"https://www.corum.fr/nos-scpi/{scpi_id}/documents",
        strategie_bulletin="scrape_listing",
        conf={},
    )


class _FakeClient:
    """Sert les fixtures ; ne touche jamais le réseau."""

    def __init__(self, html: str) -> None:
        self._html = html

    def get_text(self, url: str, **_: object) -> str:
        return self._html

    def get_bytes(self, url: str, **_: object) -> bytes:
        return b"%PDF-fake"


def test_find_latest_bulletin_picks_t2_2026():
    html = (FIX / "corum_eurion_documents.html").read_text(encoding="utf-8")
    adapter = CorumAdapter(_FakeClient(html))  # type: ignore[arg-type]
    found = adapter._find_latest_bulletin(html)
    assert found is not None
    url, year, quarter = found
    assert (year, quarter) == (2026, 2)
    assert url.startswith("https://www.corum.fr/sites/default/files/")
    assert "Fil" in url and url.lower().endswith(".pdf")


def test_extract_eurion_exact_values():
    text = (FIX / "corum_eurion_2026T2.txt").read_text(encoding="utf-8")
    adapter = CorumAdapter(_FakeClient(""))  # type: ignore[arg-type]
    metrics = adapter._extract(
        _entry("corum_eurion"), text, "https://x/eurion.pdf", "2026-T2", date(2026, 6, 30)
    )
    ok = {m.metric_key: m for m in metrics if m.status == Status.OK}

    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(1_534_000_000.0)
    assert ok[MetricKey.CAPITALISATION].confidence == Confidence.HAUTE
    assert ok[MetricKey.NOMBRE_PARTS].value_num == pytest.approx(7_135_382.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(215.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].confidence == Confidence.MOYENNE
    assert ok[MetricKey.VALEUR_RECONSTITUTION].value_num == pytest.approx(222.12)

    # Toutes les métriques OK sont datées à la fin de trimestre.
    for m in ok.values():
        assert m.published_at == date(2026, 6, 30)
        assert m.period == "2026-T2"
        assert m.source_url == "https://x/eurion.pdf"

    # Ce qui n'est pas extractible de façon sûre -> A_VERIFIER, avec le lien.
    averifier = {m.metric_key for m in metrics if m.status == Status.A_VERIFIER}
    assert MetricKey.TOF in averifier
    assert MetricKey.PRIX_RETRAIT in averifier
    for m in metrics:
        if m.status == Status.A_VERIFIER:
            assert m.value_num is None
            assert m.source_url == "https://x/eurion.pdf"


def test_extract_usa_exact_values():
    text = (FIX / "corum_usa_2026T2.txt").read_text(encoding="utf-8")
    adapter = CorumAdapter(_FakeClient(""))  # type: ignore[arg-type]
    ok = {
        m.metric_key: m
        for m in adapter._extract(
            _entry("corum_usa"), text, "https://x/usa.pdf", "2026-T2", date(2026, 6, 30)
        )
        if m.status == Status.OK
    }
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(77_000_000.0)
    assert ok[MetricKey.NOMBRE_PARTS].value_num == pytest.approx(387_121.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(200.0)
    assert ok[MetricKey.VALEUR_RECONSTITUTION].value_num == pytest.approx(203.24)


def test_scanned_pdf_all_a_verifier(monkeypatch):
    """Bulletin image (Origin/XL) : aucune extraction, tout A_VERIFIER, pas d'OCR."""
    html = (FIX / "corum_eurion_documents.html").read_text(encoding="utf-8")
    monkeypatch.setattr(corum, "extract_pdf", lambda _: PdfContent(text=""))
    adapter = CorumAdapter(_FakeClient(html))  # type: ignore[arg-type]
    metrics = adapter.fetch_metrics(_entry("corum_xl"))
    assert len(metrics) == len(TARGET_KEYS)
    assert all(m.status == Status.A_VERIFIER for m in metrics)
    assert all("image" in (m.note or "") for m in metrics)


def test_fetch_metrics_end_to_end_with_fake_client(monkeypatch):
    """fetch_metrics complet : page docs (fixture) -> PDF (texte fixture)."""
    html = (FIX / "corum_eurion_documents.html").read_text(encoding="utf-8")
    text = (FIX / "corum_eurion_2026T2.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(corum, "extract_pdf", lambda _: PdfContent(text=text))
    adapter = CorumAdapter(_FakeClient(html))  # type: ignore[arg-type]
    metrics = adapter.fetch_metrics(_entry("corum_eurion"))
    ok = [m for m in metrics if m.status == Status.OK]
    assert len(ok) == 4
    assert {m.metric_key for m in ok} == {
        MetricKey.CAPITALISATION,
        MetricKey.NOMBRE_PARTS,
        MetricKey.PRIX_SOUSCRIPTION,
        MetricKey.VALEUR_RECONSTITUTION,
    }
