"""Tests portefeuille : XIRR, PRU, +/- value, délai de jouissance, nue-propriété."""

from datetime import date

import pytest

from scpi.models import Confidence, Metric, MetricKey, now_utc
from scpi.portfolio import Ligne, compute_line, xirr
from scpi.storage import Store


def test_xirr_simple():
    # -1000 puis +1100 un an après ~ 10 %.
    r = xirr([(date(2024, 1, 1), -1000), (date(2025, 1, 1), 1100)])
    assert r == pytest.approx(0.10, abs=1e-3)


def test_xirr_needs_sign_change():
    assert xirr([(date(2024, 1, 1), -1000), (date(2025, 1, 1), -50)]) is None


def _seed(store, delai=6):
    store.upsert_scpi("x", "X", "sdg", "SDG", "x.fr")
    def m(key, val, period=None, pub=None):
        return Metric.ok_num(scpi_id="x", metric_key=key, value=val, unit=None,
                             period=period, source_url="u", published_at=pub,
                             collected_at=now_utc(), confidence=Confidence.HAUTE)
    store.insert_metrics([
        m(MetricKey.PRIX_RETRAIT, 195.0),
        m(MetricKey.PRIX_SOUSCRIPTION, 210.0),
        m(MetricKey.DELAI_JOUISSANCE, delai),
        # avant jouissance (2024-07-15) -> exclu ; après -> inclus
        m(MetricKey.ACOMPTE, 2.75, "2024-T2", date(2024, 6, 30)),
        m(MetricKey.ACOMPTE, 2.75, "2024-T3", date(2024, 9, 30)),
    ])


def test_compute_line_pleine_propriete(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    _seed(store)
    ln = Ligne(scpi_id="x", date_achat=date(2024, 1, 15), nb_parts=50, prix_unitaire=200, frais=0)
    res = compute_line(store, ln, valuation=date(2026, 6, 30))
    assert res.montant_investi == pytest.approx(10_000)
    assert res.pru == pytest.approx(200)
    assert res.prix_courant == 195.0 and res.base_prix == "prix_retrait"
    assert res.valeur_courante == pytest.approx(9_750)
    assert res.pv_latente == pytest.approx(-250)
    # Seul l'acompte du 30/09 (après jouissance) compte : 2,75 * 50 = 137,5
    assert res.dividendes_encaisses == pytest.approx(137.5)
    assert res.tri is not None
    store.close()


def test_compute_line_nue_propriete(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    _seed(store)
    ln = Ligne(scpi_id="x", date_achat=date(2024, 1, 15), nb_parts=50, prix_unitaire=200,
               propriete="nue", demembrement_annees=7)
    res = compute_line(store, ln)
    assert res.valeur_courante is None and res.tri is None
    assert res.dividendes_encaisses == 0.0
    assert any("démembrement" in n for n in res.notes)
    store.close()
