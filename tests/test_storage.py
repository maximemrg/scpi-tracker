from datetime import date

from scpi.models import Confidence, Metric, MetricKey, Status, now_utc
from scpi.storage import Store, persist_run


def _metric(scpi_id="corum_xl", value=1090.0, period="2026-T2", key=MetricKey.PRIX_SOUSCRIPTION):
    return Metric.ok_num(
        scpi_id=scpi_id,
        metric_key=key,
        value=value,
        unit="EUR",
        period=period,
        source_url="https://www.corum.fr/x.pdf",
        published_at=date(2026, 6, 30),
        collected_at=now_utc(),
    )


def test_append_only_keeps_history(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    store.insert_metrics([_metric(value=1090.0)])
    store.insert_metrics([_metric(value=1120.0)])
    rows = store.conn.execute("SELECT value_num FROM metrics ORDER BY id").fetchall()
    assert [r["value_num"] for r in rows] == [1090.0, 1120.0]  # rien écrasé
    latest = store.latest_value("corum_xl", MetricKey.PRIX_SOUSCRIPTION, "2026-T2")
    assert latest["value_num"] == 1120.0
    store.close()


def test_manual_override_wins(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    store.insert_metrics([_metric(value=1090.0)])
    store.add_override(
        scpi_id="corum_xl",
        metric_key=MetricKey.PRIX_SOUSCRIPTION,
        period="2026-T2",
        value_num=999.0,
        note="correction manuelle",
    )
    latest = store.latest_value("corum_xl", MetricKey.PRIX_SOUSCRIPTION, "2026-T2")
    assert latest["value_num"] == 999.0
    assert latest["confidence"] == "MANUELLE"
    store.close()


def test_change_detection_emits_alert(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    persist_run(store, [_metric(value=1090.0)])
    ok, av, alerts = persist_run(store, [_metric(value=1120.0)])
    assert ok == 1 and av == 0
    assert len(alerts) == 1 and "1090.0 -> 1120.0" in alerts[0]
    n = store.conn.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"]
    assert n == 1
    store.close()


def test_change_detection_no_alert_when_stable(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    persist_run(store, [_metric(value=1090.0)])
    _, _, alerts = persist_run(store, [_metric(value=1090.0)])
    assert alerts == []
    store.close()


def test_a_verifier_metric_stored_with_source(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    m = Metric.a_verifier(
        scpi_id="corum_usa",
        metric_key=MetricKey.TOF,
        source_url="https://www.corum.fr/nos-scpi/corum-usa/documents",
        collected_at=now_utc(),
        note="libellé introuvable",
    )
    store.insert_metrics([m])
    row = store.conn.execute("SELECT * FROM metrics").fetchone()
    assert row["status"] == Status.A_VERIFIER
    assert row["value_num"] is None
    assert row["source_url"].endswith("/documents")
    assert row["confidence"] == Confidence.FAIBLE
    store.close()
