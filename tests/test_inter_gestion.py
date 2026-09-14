"""Tests adaptateur Inter Gestion (fiches HTML aplaties, figées)."""

from pathlib import Path

import pytest

from scpi.models import MetricKey, Status
from scpi.registry import ScpiEntry
from scpi.sources.inter_gestion import InterGestionAdapter

FIX = Path(__file__).parent / "fixtures"


def _entry(scpi_id: str) -> ScpiEntry:
    return ScpiEntry(
        scpi_id=scpi_id, nom=scpi_id, sdg_key="inter_gestion_reim", sdg_nom="Inter Gestion REIM",
        domaine="inter-gestion.com",
        fiche_url=f"https://www.inter-gestion.com/offre-scpi/{scpi_id.replace('_','-')}",
        documents_url=None, strategie_bulletin="html_site", conf={},
    )


def _ok(scpi_id: str):
    text = (FIX / f"inter_gestion_{scpi_id}.txt").read_text(encoding="utf-8")
    adapter = InterGestionAdapter(None)  # type: ignore[arg-type]
    ms = adapter._extract(_entry(scpi_id), text, "https://x/")
    return {m.metric_key: m for m in ms if m.status == Status.OK}


def test_cristal_rente_value_before_label():
    ok = _ok("cristal_rente")
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(255.68)
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(684_000_000.0)
    assert ok[MetricKey.TRI_10ANS].value_num == pytest.approx(5.56)


def test_cristal_life_capitalisation():
    ok = _ok("cristal_life")
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(424_000_000.0)
    # Valeur IFI (214/212) NE doit PAS être prise pour reconstitution/réalisation.
    assert MetricKey.VALEUR_RECONSTITUTION not in ok
