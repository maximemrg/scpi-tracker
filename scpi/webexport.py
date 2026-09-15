"""Export d'un mini-site HTML AUTONOME (un seul fichier, à intégrer ailleurs).

Onglets (côté client, sans backend) : Tableau de bord, Screener, Sources,
À vérifier, + fiche SCPI en modale (métriques + graphes d'historique).
Instantané en lecture seule : la saisie manuelle reste dans l'app locale.
On régénère le fichier après chaque collecte / correction.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import dataview
from .models import MetricKey
from .storage import Store

_TPL_DIR = Path(__file__).parent / "web" / "templates"
_HISTORY_KEYS = [MetricKey.PRIX_SOUSCRIPTION, MetricKey.PRIX_RETRAIT,
                 MetricKey.TAUX_DISTRIBUTION, MetricKey.CAPITALISATION, MetricKey.ACOMPTE]


def _details(store: Store, scpi_id: str) -> dict[str, Any]:
    metrics = []
    for key in MetricKey:
        c = dataview.current_cell(store, scpi_id, str(key))
        if c is None:
            continue
        metrics.append({
            "key": str(key), "label": str(key).replace("_", " "),
            "value": c.value, "unit": c.unit, "confidence": c.confidence,
            "status": c.status, "period": c.period, "published": c.published_at,
            "source": c.source_url,
        })
    history = {}
    for k in _HISTORY_KEYS:
        pts = dataview.history(store, scpi_id, str(k))
        if pts:
            history[str(k)] = {"label": str(k).replace("_", " "), "points": pts}
    return {"metrics": metrics, "history": history}


def export_html(store: Store, out_path: str | Path) -> Path:
    rows = dataview.screener_rows(store)
    tds = [r["ind"]["td"] for r in rows if r["ind"]["td"] is not None]
    n_ok = store.conn.execute("SELECT COUNT(*) c FROM metrics WHERE status='OK'").fetchone()["c"]
    n_av = store.conn.execute(
        "SELECT COUNT(*) c FROM metrics WHERE status='A_VERIFIER'").fetchone()["c"]
    kpis = {
        "n_scpi": len(rows),
        "td_moyen": round(sum(tds) / len(tds), 2) if tds else None,
        "n_ok": n_ok, "n_av": n_av,
    }
    chart_data = [
        {"nom": r["scpi"]["nom"], "scpi_id": r["scpi"]["scpi_id"],
         "td": r["ind"]["td"], "ecart": r["ind"]["ecart"]}
        for r in rows
    ]
    details = {
        r["scpi"]["scpi_id"]: {
            "nom": r["scpi"]["nom"], "sdg": r["scpi"]["sdg_nom"],
            **_details(store, r["scpi"]["scpi_id"]),
        }
        for r in rows
    }
    env = Environment(loader=FileSystemLoader(str(_TPL_DIR)), autoescape=select_autoescape())
    html = env.get_template("export.html").render(
        rows=rows, cols=dataview.SCREENER_COLS, kpis=kpis, chart_data=chart_data,
        sources=dataview.sources(store), averifier=dataview.a_verifier(store),
        details=details, generated=date.today().isoformat(),
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
