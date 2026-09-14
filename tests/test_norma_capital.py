"""Tests adaptateur Norma Capital (source = HTML du site officiel, figé)."""

from datetime import date
from pathlib import Path

import pytest

from scpi.models import Confidence, MetricKey, Status
from scpi.registry import ScpiEntry
from scpi.sources.norma_capital import NormaCapitalAdapter

FIX = Path(__file__).parent / "fixtures"
HOME = (FIX / "norma_capital_home.html").read_text(encoding="utf-8")


class _FakeClient:
    def get_text(self, url: str, **_: object) -> str:
        return HOME


def _entry(scpi_id: str) -> ScpiEntry:
    return ScpiEntry(
        scpi_id=scpi_id, nom=scpi_id, sdg_key="norma_capital", sdg_nom="Norma Capital",
        domaine="normacapital.fr",
        fiche_url=f"https://www.normacapital.fr/nos-offres-grand-public/{scpi_id}/",
        documents_url=f"https://www.normacapital.fr/nos-offres-grand-public/{scpi_id}/",
        strategie_bulletin="html_site", conf={},
    )


def _ok(scpi_id: str) -> dict[str, object]:
    metrics = NormaCapitalAdapter(_FakeClient()).fetch_metrics(_entry(scpi_id))  # type: ignore[arg-type]
    return {m.metric_key: m for m in metrics if m.status == Status.OK}


def test_ncap_regions_values():
    ok = _ok("ncap_regions")
    assert ok[MetricKey.TAUX_DISTRIBUTION].value_num == pytest.approx(7.51)
    assert ok[MetricKey.TAUX_DISTRIBUTION].period == "2025"
    assert ok[MetricKey.TRI_5ANS].value_num == pytest.approx(5.44)
    assert ok[MetricKey.TRI_5ANS].period == "2020-2025"
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(1_106_700_000.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(682.0)
    assert all(m.confidence == Confidence.HAUTE for m in ok.values())
    assert ok[MetricKey.CAPITALISATION].published_at == date(2026, 6, 30)


def test_fair_invest_values():
    ok = _ok("fair_invest")
    assert ok[MetricKey.TAUX_DISTRIBUTION].value_num == pytest.approx(4.52)
    assert ok[MetricKey.TRI_5ANS].value_num == pytest.approx(2.87)
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(118_700_000.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(202.0)


def test_ncap_continent_no_tri5():
    """Continent (jeune SCPI) n'affiche pas de TRI 5 ans -> A_VERIFIER, pas de valeur inventée."""
    metrics = NormaCapitalAdapter(_FakeClient()).fetch_metrics(_entry("ncap_continent"))  # type: ignore[arg-type]
    ok = {m.metric_key: m for m in metrics if m.status == Status.OK}
    av = {m.metric_key for m in metrics if m.status == Status.A_VERIFIER}
    assert ok[MetricKey.TAUX_DISTRIBUTION].value_num == pytest.approx(7.10)
    assert ok[MetricKey.CAPITALISATION].value_num == pytest.approx(81_500_000.0)
    assert ok[MetricKey.PRIX_SOUSCRIPTION].value_num == pytest.approx(210.0)
    assert MetricKey.TRI_5ANS in av  # non affiché -> A_VERIFIER


def test_tof_and_associes_are_a_verifier():
    metrics = NormaCapitalAdapter(_FakeClient()).fetch_metrics(_entry("ncap_regions"))  # type: ignore[arg-type]
    av = {m.metric_key: m for m in metrics if m.status == Status.A_VERIFIER}
    assert MetricKey.TOF in av
    assert MetricKey.NOMBRE_ASSOCIES in av
    # A_VERIFIER sourcé sur la page SCPI (pas la home).
    assert av[MetricKey.TOF].source_url.endswith("/")
