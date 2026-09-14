"""Test adaptateur Arkéa : extrait le réel, ignore les tuiles placeholder à 0."""

from pathlib import Path

import pytest

from scpi.models import MetricKey, Status
from scpi.registry import ScpiEntry
from scpi.sources.arkea import ArkeaAdapter

FIX = Path(__file__).parent / "fixtures"


def _run(scpi_id: str):
    text = (FIX / f"arkea_{scpi_id}.txt").read_text(encoding="utf-8")
    adapter = ArkeaAdapter(None)  # type: ignore[arg-type]

    class _C:
        def get_text(self, *_a, **_k): return text
    adapter.client = _C()  # type: ignore[assignment]
    ms = adapter.fetch_metrics(ScpiEntry(
        scpi_id=scpi_id, nom="x", sdg_key="arkea_reim", sdg_nom="Arkéa REIM",
        domaine="arkea-reim.com", fiche_url="https://x/", documents_url="https://x/",
        strategie_bulletin="html_site", conf={}))
    return ({m.metric_key: m for m in ms if m.status == Status.OK},
            {m.metric_key for m in ms if m.status == Status.A_VERIFIER})


def test_transitions_europe():
    ok, av = _run("transitions_europe")
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(1_380_000_000.0)
    assert ok[MetricKey.PRIX_RETRAIT].value_num == pytest.approx(181.80)
    assert ok[MetricKey.FRAIS_GESTION].value_num == pytest.approx(10.0)
    assert ok[MetricKey.DELAI_JOUISSANCE].value_num == pytest.approx(6)
    # Tuiles à 0 (JS) non extraites -> A_VERIFIER, pas de faux 0.
    assert MetricKey.TOF in av
    assert MetricKey.NOMBRE_IMMEUBLES in av


def test_momentime_capitalisation():
    ok, _ = _run("momentime")
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(48_800_000.0)
    assert ok[MetricKey.FRAIS_GESTION].value_num == pytest.approx(10.0)
