"""Export d'une page HTML AUTONOME (à intégrer dans un site tiers).

Instantané en lecture seule (données embarquées + Chart.js via CDN). La saisie
manuelle n'y figure pas : elle nécessite le backend local. On régénère la page
après chaque collecte / correction pour la mettre à jour.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import dataview
from .storage import Store

_TPL_DIR = Path(__file__).parent / "web" / "templates"


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
    env = Environment(loader=FileSystemLoader(str(_TPL_DIR)), autoescape=select_autoescape())
    html = env.get_template("export.html").render(
        rows=rows, cols=dataview.SCREENER_COLS, kpis=kpis, chart_data=chart_data,
        generated=date.today().isoformat(),
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
