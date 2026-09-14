"""Tests de l'adaptateur Corum sur fixtures RÉELLES figées (bulletin T2 2026).

Les fixtures *.pdfcontent.json sont le dump réel de pdfplumber (texte + tableaux
+ mots positionnés). Ces tests cassent si Corum change la mise en page — c'est
leur rôle. Ils garantissent AUSSI qu'aucune valeur fausse n'est produite :
nombre_associés / TOF restent en A_VERIFIER (extraction non sûre).
"""

import json
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
        scpi_id=scpi_id, nom=scpi_id, sdg_key="corum_lepargne", sdg_nom="Corum L'Épargne",
        domaine="corum.fr", fiche_url=f"https://www.corum.fr/nos-scpi/{scpi_id}",
        documents_url=f"https://www.corum.fr/nos-scpi/{scpi_id}/documents",
        strategie_bulletin="scrape_listing", conf={},
    )


def _content(scpi_id: str) -> PdfContent:
    d = json.loads((FIX / f"{scpi_id}_2026T2.pdfcontent.json").read_text(encoding="utf-8"))
    return PdfContent(text=d["text"], tables=d["tables"], words=d["words"])


class _FakeClient:
    def __init__(self, html: str = "") -> None:
        self._html = html

    def get_text(self, url: str, **_: object) -> str:
        return self._html

    def get_bytes(self, url: str, **_: object) -> bytes:
        return b"%PDF-fake"


def _extract(scpi_id: str) -> dict[str, object]:
    adapter = CorumAdapter(_FakeClient())  # type: ignore[arg-type]
    metrics = adapter._extract(
        _entry(scpi_id), _content(scpi_id), f"https://x/{scpi_id}.pdf",
        "2026-T2", date(2026, 6, 30),
    )
    return {"ok": {m.metric_key: m for m in metrics if m.status == Status.OK},
            "averifier": {m.metric_key for m in metrics if m.status == Status.A_VERIFIER}}


def test_find_latest_bulletin_picks_t2_2026():
    html = (FIX / "corum_eurion_documents.html").read_text(encoding="utf-8")
    adapter = CorumAdapter(_FakeClient(html))  # type: ignore[arg-type]
    result = adapter._find_latest_bulletin(html)
    assert result is not None
    url, year, quarter = result
    assert (year, quarter) == (2026, 2)
    assert url.startswith("https://www.corum.fr/sites/default/files/")
    assert url.lower().endswith(".pdf")


def test_extract_eurion_exact_values():
    r = _extract("corum_eurion")
    ok = r["ok"]  # type: ignore[assignment]
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(1_534_000_000.0)
    assert ok[MetricKey.NOMBRE_PARTS].value_num == pytest.approx(7_135_382.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(215.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].confidence == Confidence.MOYENNE
    assert ok[MetricKey.VALEUR_RECONSTITUTION].value_num == pytest.approx(222.12)
    assert ok[MetricKey.VALEUR_REALISATION].value_num == pytest.approx(177.10)
    assert ok[MetricKey.ACOMPTE].value_num == pytest.approx(2.75)
    assert ok[MetricKey.NOMBRE_IMMEUBLES].value_num == pytest.approx(54.0)

    td = ok[MetricKey.TAUX_DISTRIBUTION]
    assert td.value_num == pytest.approx(5.73)
    assert td.period == "2025"  # TD daté sur l'année, pas sur le trimestre
    assert td.confidence == Confidence.HAUTE

    # Non sûrs -> A_VERIFIER (jamais de valeur devinée).
    assert MetricKey.NOMBRE_ASSOCIES in r["averifier"]
    assert MetricKey.TOF in r["averifier"]


def test_extract_usa_exact_values():
    r = _extract("corum_usa")
    ok = r["ok"]  # type: ignore[assignment]
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(77_000_000.0)
    assert ok[MetricKey.NOMBRE_PARTS].value_num == pytest.approx(387_121.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(200.0)
    assert ok[MetricKey.VALEUR_RECONSTITUTION].value_num == pytest.approx(203.24)
    assert ok[MetricKey.VALEUR_REALISATION].value_num == pytest.approx(177.04)
    assert ok[MetricKey.TAUX_DISTRIBUTION].value_num == pytest.approx(7.70)
    assert ok[MetricKey.NOMBRE_IMMEUBLES].value_num == pytest.approx(5.0)
    # USA n'a pas de cellule "Dividende brut trimestriel" -> acompte A_VERIFIER.
    assert MetricKey.ACOMPTE in r["averifier"]


def test_scanned_pdf_all_a_verifier(monkeypatch):
    html = (FIX / "corum_eurion_documents.html").read_text(encoding="utf-8")
    monkeypatch.setattr(corum, "extract_pdf", lambda _: PdfContent(text=""))
    metrics = CorumAdapter(_FakeClient(html)).fetch_metrics(_entry("corum_xl"))  # type: ignore[arg-type]
    assert len(metrics) == len(TARGET_KEYS)
    assert all(m.status == Status.A_VERIFIER for m in metrics)
    assert all("image" in (m.note or "") for m in metrics)


def test_fetch_metrics_end_to_end(monkeypatch):
    html = (FIX / "corum_eurion_documents.html").read_text(encoding="utf-8")
    monkeypatch.setattr(corum, "extract_pdf", lambda _: _content("corum_eurion"))
    metrics = CorumAdapter(_FakeClient(html)).fetch_metrics(_entry("corum_eurion"))  # type: ignore[arg-type]
    ok = {m.metric_key for m in metrics if m.status == Status.OK}
    assert ok == {
        MetricKey.CAPITALISATION, MetricKey.NOMBRE_PARTS, MetricKey.PRIX_SOUSCRIPTION,
        MetricKey.VALEUR_RECONSTITUTION, MetricKey.VALEUR_REALISATION,
        MetricKey.TAUX_DISTRIBUTION, MetricKey.ACOMPTE, MetricKey.NOMBRE_IMMEUBLES,
    }
