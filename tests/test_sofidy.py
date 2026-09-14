"""Tests adaptateur Sofidy + parsing de période Sofidy."""

from pathlib import Path

import pytest

from scpi.models import Status
from scpi.pdf import PdfContent
from scpi.registry import ScpiEntry
from scpi.sources import sofidy
from scpi.sources.sofidy import TARGET_KEYS, SofidyAdapter, sofidy_period

FIX = Path(__file__).parent / "fixtures"


def _entry(scpi_id: str, docs: str) -> ScpiEntry:
    return ScpiEntry(
        scpi_id=scpi_id, nom=scpi_id, sdg_key="sofidy", sdg_nom="Sofidy",
        domaine="sofidy.com", fiche_url=docs, documents_url=docs,
        strategie_bulletin="scrape_listing", conf={},
    )


class _FakeClient:
    def __init__(self, html: str = "") -> None:
        self._html = html

    def get_text(self, url: str, **_: object) -> str:
        return self._html

    def get_bytes(self, url: str, **_: object) -> bytes:
        return b"%PDF-fake"


@pytest.mark.parametrize("text,expected", [
    ("Bulletin Trimestriel - T2 2026", (2026, 2)),
    ("immorente-bulletin-trimestriel-2t24.pdf", (2024, 2)),
    ("Bulletin_Trimestriel_-_Immorente_2026_2T_OPTI.pdf", (2026, 2)),
    ("IMMORENTE-BT-1T-2026-1.pdf", (2026, 1)),
    ("Bulletin Trimestriel T4 - 2021", (2021, 4)),
    ("sei-bulletin-trimestriel-4t24.pdf", (2024, 4)),
    ("rien du tout", None),
])
def test_sofidy_period(text, expected):
    assert sofidy_period(text) == expected


def test_find_latest_bulletin_immorente():
    html = (FIX / "sofidy_immorente_documents.html").read_text(encoding="utf-8")
    found = SofidyAdapter(_FakeClient(html))._find_latest_bulletin(html)  # type: ignore[arg-type]
    assert found is not None
    url, year, quarter = found
    # Le plus récent des bulletins de la fixture réelle est T2 2026.
    assert (year, quarter) == (2026, 2)
    assert url.startswith("https://www.sofidy.com/app/uploads/") and url.lower().endswith(".pdf")


def test_cid_font_all_a_verifier_but_sourced(monkeypatch):
    """Bulletin à police vectorisée -> tout A_VERIFIER, mais sourcé au bon PDF."""
    html = (FIX / "sofidy_immorente_documents.html").read_text(encoding="utf-8")
    fake = PdfContent(text="TOF (cid:31)(cid:30) CAPITALISATION (cid:24) blah " * 5)
    monkeypatch.setattr(sofidy, "extract_pdf", lambda _: fake)
    entry = _entry("immorente", "https://www.sofidy.com/documentation/")
    metrics = SofidyAdapter(_FakeClient(html)).fetch_metrics(entry)  # type: ignore[arg-type]
    assert len(metrics) == len(TARGET_KEYS)
    assert all(m.status == Status.A_VERIFIER for m in metrics)
    assert all(m.value_num is None for m in metrics)
    assert all("vectorisée" in (m.note or "") for m in metrics)
    # Sourcé sur le PDF daté, pas sur la page documents.
    assert all(m.source_url.endswith(".pdf") for m in metrics)
    assert all(m.period == "2026-T2" for m in metrics)
