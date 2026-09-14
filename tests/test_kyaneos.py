"""Tests adaptateur Kyaneos (fiche HTML figée) + SCPI fiscale sans URL."""

from pathlib import Path

import pytest

from scpi.models import MetricKey, Status
from scpi.registry import ScpiEntry
from scpi.sources.kyaneos import TARGET_KEYS, KyaneosAdapter

FIX = Path(__file__).parent / "fixtures"


def _entry(scpi_id: str, fiche: str | None) -> ScpiEntry:
    return ScpiEntry(
        scpi_id=scpi_id, nom=scpi_id, sdg_key="kyaneos_am", sdg_nom="Kyaneos AM",
        domaine="kyaneosam.com", fiche_url=fiche, documents_url=fiche,
        strategie_bulletin="html_site", conf={},
    )


def test_kyaneos_pierre_values():
    text = (FIX / "kyaneos_pierre.txt").read_text(encoding="utf-8")
    adapter = KyaneosAdapter(None)  # type: ignore[arg-type]
    ms = adapter._extract(_entry("kyaneos_pierre", "https://x/"), text, "https://x/")
    ok = {m.metric_key: m for m in ms if m.status == Status.OK}
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(224.0)
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(453_000_000.0)
    assert ok[MetricKey.NOMBRE_ASSOCIES].value_num == pytest.approx(11_091)
    assert ok[MetricKey.DELAI_JOUISSANCE].value_num == pytest.approx(6)


def test_denormandie5_without_url_all_a_verifier():
    """SCPI fiscale sans URL confirmée -> tout A_VERIFIER, aucune valeur inventée."""
    adapter = KyaneosAdapter(None)  # type: ignore[arg-type]
    ms = adapter.fetch_metrics(_entry("kyaneos_denormandie_5", None))
    assert len(ms) == len(TARGET_KEYS)
    assert all(m.status == Status.A_VERIFIER and m.value_num is None for m in ms)
