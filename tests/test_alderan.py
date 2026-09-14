"""Tests adaptateur Alderan (source HTML aplati, fixtures figées)."""

from datetime import date
from pathlib import Path

import pytest

from scpi.models import Confidence, MetricKey, Status
from scpi.registry import ScpiEntry
from scpi.sources.alderan import AlderanAdapter

FIX = Path(__file__).parent / "fixtures"


def _entry(scpi_id: str) -> ScpiEntry:
    return ScpiEntry(
        scpi_id=scpi_id, nom=scpi_id, sdg_key="alderan", sdg_nom="Alderan",
        domaine="alderan.fr", fiche_url=f"https://alderan.fr/scpi-{scpi_id}/",
        documents_url=f"https://alderan.fr/scpi-{scpi_id}-documentation/",
        strategie_bulletin="html_site", conf={},
    )


def _extract(scpi_id: str):
    text = (FIX / f"alderan_{scpi_id}.txt").read_text(encoding="utf-8")
    adapter = AlderanAdapter(None)  # type: ignore[arg-type]  # _extract ne touche pas au client
    ms = adapter._extract(_entry(scpi_id), text, f"https://alderan.fr/scpi-{scpi_id}/")
    return ({m.metric_key: m for m in ms if m.status == Status.OK},
            {m.metric_key: m for m in ms if m.status == Status.A_VERIFIER})


def test_activimmo_values():
    ok, av = _extract("activimmo")
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(613.50)
    assert ok[MetricKey.PRIX_RETRAIT].value_num == pytest.approx(548.47)
    assert ok[MetricKey.VALEUR_REALISATION].value_num == pytest.approx(507.98)
    assert ok[MetricKey.VALEUR_REALISATION].published_at == date(2026, 6, 30)
    assert ok[MetricKey.TOF].value_num == pytest.approx(93.30)
    assert ok[MetricKey.NOMBRE_IMMEUBLES].value_num == pytest.approx(182)
    assert ok[MetricKey.NOMBRE_ASSOCIES].value_num == pytest.approx(29_843)
    assert ok[MetricKey.DELAI_JOUISSANCE].value_num == pytest.approx(6)
    # Piège évité : "Taux de distribution dont 0,31%..." -> PAS extrait comme TD.
    assert MetricKey.TAUX_DISTRIBUTION in av


def test_comete_values():
    ok, av = _extract("comete")
    assert ok[MetricKey.TAUX_DISTRIBUTION].value_num == pytest.approx(6.00)
    assert ok[MetricKey.TAUX_DISTRIBUTION].period == "2025"
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(250.0)
    assert ok[MetricKey.PRIX_RETRAIT].value_num == pytest.approx(225.0)
    assert ok[MetricKey.VALEUR_REALISATION].value_num == pytest.approx(217.17)
    assert ok[MetricKey.DELAI_JOUISSANCE].value_num == pytest.approx(6)
    assert all(
        m.confidence == Confidence.HAUTE
        for k, m in ok.items() if k != MetricKey.NOMBRE_ASSOCIES
    )


def test_monthly_dividend_acompte_is_a_verifier_with_note():
    _, av = _extract("comete")
    assert MetricKey.ACOMPTE in av
    assert "MENSUEL" in av[MetricKey.ACOMPTE].note.upper()
