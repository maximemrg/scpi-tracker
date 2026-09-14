"""Test adaptateur Perial : seul le TD 2025 est extrait (grille Webflow ambiguë)."""

from pathlib import Path

import pytest

from scpi.models import Confidence, MetricKey, Status
from scpi.registry import ScpiEntry
from scpi.sources.perial import PerialAdapter

FIX = Path(__file__).parent / "fixtures"
EXPECTED = {"pfo": 6.10, "pfo2": 4.65, "pf_grand_paris": 4.80, "pf_hospitalite_europe": 4.11}


@pytest.mark.parametrize("scpi_id,td", EXPECTED.items())
def test_perial_td_only(scpi_id, td):
    text = (FIX / f"perial_{scpi_id}.txt").read_text(encoding="utf-8")
    adapter = PerialAdapter(None)  # type: ignore[arg-type]

    class _C:
        def get_text(self, *_a, **_k): return text
    adapter.client = _C()  # type: ignore[assignment]
    ms = adapter.fetch_metrics(ScpiEntry(
        scpi_id=scpi_id, nom="x", sdg_key="perial_am", sdg_nom="Perial",
        domaine="perial.com", fiche_url="https://x/", documents_url="https://x/",
        strategie_bulletin="html_site", conf={}))
    ok = {m.metric_key: m for m in ms if m.status == Status.OK}
    assert ok[MetricKey.TAUX_DISTRIBUTION].value_num == pytest.approx(td)
    assert ok[MetricKey.TAUX_DISTRIBUTION].confidence == Confidence.MOYENNE
    # Les autres KPI ne sont pas devinés (grille ambiguë).
    assert MetricKey.CAPITALISATION not in ok
