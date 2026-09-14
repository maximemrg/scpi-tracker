"""Tests adaptateur Sogenial (fiches HTML aplaties, figées)."""

from pathlib import Path

import pytest

from scpi.models import MetricKey, Status
from scpi.registry import ScpiEntry
from scpi.sources.sogenial import SogenialAdapter

FIX = Path(__file__).parent / "fixtures"


def _entry(scpi_id: str) -> ScpiEntry:
    return ScpiEntry(
        scpi_id=scpi_id, nom=scpi_id, sdg_key="sogenial_immobilier", sdg_nom="Sogenial",
        domaine="sogenial.fr", fiche_url=f"https://www.sogenial.fr/societe/scpi-{scpi_id}/",
        documents_url=None, strategie_bulletin="html_site", conf={},
    )


def _ok(scpi_id: str):
    text = (FIX / f"sogenial_{scpi_id}.txt").read_text(encoding="utf-8")
    adapter = SogenialAdapter(None)  # type: ignore[arg-type]
    ms = adapter._extract(_entry(scpi_id), text, "https://x/")
    return ({m.metric_key: m for m in ms if m.status == Status.OK},
            {m.metric_key for m in ms if m.status == Status.A_VERIFIER})


def test_coeur_de_regions():
    ok, _ = _ok("coeur_de_regions")
    assert ok[MetricKey.TAUX_DISTRIBUTION].value_num == pytest.approx(6.20)
    assert ok[MetricKey.TAUX_DISTRIBUTION].period == "2025"
    assert ok[MetricKey.TRI_5ANS].value_num == pytest.approx(4.44)
    assert ok[MetricKey.PRIX_RETRAIT].value_num == pytest.approx(584.32)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(664.0)
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(441_400_000.0)
    assert ok[MetricKey.DELAI_JOUISSANCE].value_num == pytest.approx(6)


def test_coeur_deurope():
    ok, _ = _ok("coeur_deurope")
    assert ok[MetricKey.TAUX_DISTRIBUTION].value_num == pytest.approx(6.25)
    assert ok[MetricKey.PRIX_RETRAIT].value_num == pytest.approx(179.52)
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(275_400_000.0)


def test_coeur_davenir_integer_prices_and_na_tri():
    """Prix sans décimale (200/180 €) extraits ; TRI 'N/A' -> A_VERIFIER."""
    ok, av = _ok("coeur_davenir")
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(200.0)
    assert ok[MetricKey.PRIX_RETRAIT].value_num == pytest.approx(180.0)
    assert MetricKey.TRI_5ANS in av  # "N/A (historique < 5 ans)" -> pas de valeur
