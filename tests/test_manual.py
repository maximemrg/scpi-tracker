"""Tests du volet saisie manuelle (gabarit A_VERIFIER -> manual_overrides)."""

from scpi.manual import generate_template, import_template
from scpi.models import Metric, MetricKey, now_utc
from scpi.storage import Store


def _averifier(store, scpi_id, key, period="2026-T2", url="https://x/b.pdf"):
    store.insert_metrics([Metric.a_verifier(
        scpi_id=scpi_id, metric_key=key, source_url=url,
        collected_at=now_utc(), note="police vectorisée", period=period,
    )])


def test_template_roundtrip(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    _averifier(store, "immorente", MetricKey.TOF)
    _averifier(store, "immorente", MetricKey.CAPITALISATION)

    tpl = tmp_path / "saisie.yaml"
    n = generate_template(store, tpl)
    assert n == 2
    text = tpl.read_text(encoding="utf-8")
    assert "immorente" in text and "source_url" in text

    # L'utilisateur complète une valeur (on simule en réécrivant le YAML).
    import yaml
    data = yaml.safe_load(tpl.read_text(encoding="utf-8"))
    for item in data["overrides"]:
        if item["metric_key"] == MetricKey.TOF:
            item["value"] = 91.17
            item["unit"] = "%"
    tpl.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    imported = import_template(store, tpl)
    assert imported == 1

    latest = store.latest_value("immorente", MetricKey.TOF, "2026-T2")
    assert latest["value_num"] == 91.17
    assert latest["confidence"] == "MANUELLE"  # gagne sur A_VERIFIER
    store.close()


def test_template_skips_existing_override(tmp_path):
    store = Store(tmp_path / "t.sqlite")
    _averifier(store, "immorente", MetricKey.TOF)
    store.add_override(
        scpi_id="immorente", metric_key=MetricKey.TOF, period="2026-T2",
        value_num=91.17, note="déjà saisi",
    )
    # Comme un override existe déjà, le gabarit ne le repropose pas.
    n = generate_template(store, tmp_path / "s.yaml")
    assert n == 0
    store.close()
