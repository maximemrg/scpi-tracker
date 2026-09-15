"""Tests de l'application web (FastAPI TestClient) : pages + saisie manuelle."""

from datetime import date

from fastapi.testclient import TestClient

from scpi.models import Confidence, Metric, MetricKey, now_utc
from scpi.storage import Store
from scpi.web import app as webapp


def _client(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    store.upsert_scpi(
        "corum_eurion", "Corum Eurion", "corum_lepargne", "Corum L'Épargne", "corum.fr"
    )
    store.insert_metrics([
        Metric.ok_num(scpi_id="corum_eurion", metric_key=MetricKey.TAUX_DISTRIBUTION,
                      value=5.73, unit="%", period="2025", source_url="https://corum.fr/x.pdf",
                      published_at=date(2026, 6, 30), collected_at=now_utc(),
                      confidence=Confidence.HAUTE),
        Metric.a_verifier(scpi_id="corum_eurion", metric_key=MetricKey.TOF,
                          source_url="https://corum.fr/x.pdf", collected_at=now_utc(),
                          note="illisible"),
    ])
    webapp.app.dependency_overrides[webapp.get_store] = lambda: store
    return TestClient(webapp.app), store


def test_pages_render(tmp_path):
    client, store = _client(tmp_path)
    for path in ["/", "/comparatif", "/a-verifier", "/sources", "/scpi/corum_eurion"]:
        r = client.get(path)
        assert r.status_code == 200
    assert "Corum Eurion" in client.get("/comparatif").text
    detail = client.get("/scpi/corum_eurion").text
    assert "5,73" in detail or "5.73" in detail
    store.close()
    webapp.app.dependency_overrides.clear()


def test_history_api(tmp_path):
    client, store = _client(tmp_path)
    r = client.get("/api/history/corum_eurion/taux_distribution")
    assert r.status_code == 200
    data = r.json()
    assert data and data[0]["value"] == 5.73
    store.close()
    webapp.app.dependency_overrides.clear()


def test_manual_override_via_web(tmp_path):
    client, store = _client(tmp_path)
    # Le TOF est en A_VERIFIER : on le saisit via le formulaire web.
    # La période postée est celle pré-remplie par la ligne A_VERIFIER (ici vide/None).
    r = client.post("/override", data={
        "scpi_id": "corum_eurion", "metric_key": MetricKey.TOF,
        "value": "97,5", "unit": "%", "source_url": "https://corum.fr/x.pdf",
    }, follow_redirects=False)
    assert r.status_code == 303
    latest = store.latest_value("corum_eurion", MetricKey.TOF)
    assert latest["value_num"] == 97.5
    assert latest["confidence"] == "MANUELLE"  # prioritaire
    # Et il ne doit plus apparaître dans la liste À vérifier.
    from scpi import dataview
    assert not any(a["metric_key"] == MetricKey.TOF
                   for a in dataview.a_verifier(store, "corum_eurion"))
    store.close()
    webapp.app.dependency_overrides.clear()


def test_export_html(tmp_path):
    from scpi.webexport import export_html
    store = Store(tmp_path / "t.sqlite")
    store.upsert_scpi(
        "corum_eurion", "Corum Eurion", "corum_lepargne", "Corum L'Épargne", "corum.fr"
    )
    store.insert_metrics([Metric.ok_num(
        scpi_id="corum_eurion", metric_key=MetricKey.TAUX_DISTRIBUTION, value=5.73, unit="%",
        period="2025", source_url="u", published_at=date(2026, 6, 30), collected_at=now_utc(),
        confidence=Confidence.HAUTE)])
    out = export_html(store, tmp_path / "public" / "scpi.html")
    html = out.read_text(encoding="utf-8")
    assert out.exists()
    assert "Corum Eurion" in html and "<canvas" in html and "scpi-embed" in html
    assert "127.0.0.1" not in html  # autonome : aucune dépendance au backend local
    store.close()
