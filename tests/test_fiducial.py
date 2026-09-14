"""Test adaptateur Fiducial (grille HTML ambiguë : on n'extrait que le sûr)."""

from pathlib import Path

import pytest

from scpi.models import MetricKey, Status
from scpi.registry import ScpiEntry
from scpi.sources.fiducial import FiducialAdapter

FIX = Path(__file__).parent / "fixtures"


def test_selectipierre2_only_unambiguous():
    text = (FIX / "fiducial_selectipierre2.txt").read_text(encoding="utf-8")
    adapter = FiducialAdapter(None)  # type: ignore[arg-type]

    class _C:
        def get_text(self, *_a, **_k): return text
    adapter.client = _C()  # type: ignore[assignment]
    ms = adapter.fetch_metrics(ScpiEntry(
        scpi_id="selectipierre_2", nom="x", sdg_key="fiducial_gerance", sdg_nom="Fiducial",
        domaine="fiducial-gerance.fr", fiche_url="https://x/", documents_url="https://x/",
        strategie_bulletin="html_site", conf={}))
    ok = {m.metric_key: m for m in ms if m.status == Status.OK}
    av = {m.metric_key for m in ms if m.status == Status.A_VERIFIER}
    assert ok[MetricKey.PRIX_RETRAIT].value_num == pytest.approx(695.70)
    assert ok[MetricKey.TOF].value_num == pytest.approx(95.05)
    assert ok[MetricKey.DELAI_JOUISSANCE].value_num == pytest.approx(2)
    # Grille ambiguë : reconstitution/réalisation NON extraites (appariement faux).
    assert MetricKey.VALEUR_RECONSTITUTION in av
    assert MetricKey.VALEUR_REALISATION in av
    assert MetricKey.TAUX_DISTRIBUTION in av
