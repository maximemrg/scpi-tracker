"""Application web locale : exploration des données, saisie manuelle, historiques.

Lecture de data/scpi.sqlite (surchargeable via $SCPI_DB). La saisie manuelle
écrit dans `manual_overrides` (confiance MANUELLE, prioritaire, conservée) —
exactement la même boucle que le CLI, mais dans le navigateur.

Lancement : `make web` ou `uvicorn scpi.web.app:app`. Bind localhost par défaut.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import dataview
from ..models import MetricKey
from ..parsing import parse_number_fr
from ..storage import Store

DB_PATH = os.environ.get("SCPI_DB", "data/scpi.sqlite")
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

SCREENER = dataview.SCREENER_COLS
_HISTORY_KEYS = [MetricKey.PRIX_SOUSCRIPTION, MetricKey.PRIX_RETRAIT,
                 MetricKey.TAUX_DISTRIBUTION, MetricKey.CAPITALISATION, MetricKey.ACOMPTE]

app = FastAPI(title="SCPI Tracker")


def get_store() -> Iterator[Store]:
    store = Store(DB_PATH)
    try:
        yield store
    finally:
        store.close()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, store: Store = Depends(get_store)) -> Any:
    rows = dataview.screener_rows(store)
    n_scpi = len(rows)
    tds = [r["ind"]["td"] for r in rows if r["ind"]["td"] is not None]
    n_ok = store.conn.execute("SELECT COUNT(*) c FROM metrics WHERE status='OK'").fetchone()["c"]
    n_av = store.conn.execute(
        "SELECT COUNT(*) c FROM metrics WHERE status='A_VERIFIER'").fetchone()["c"]
    kpis = {
        "n_scpi": n_scpi,
        "td_moyen": round(sum(tds) / len(tds), 2) if tds else None,
        "n_ok": n_ok, "n_av": n_av,
    }
    chart_data = [
        {"nom": r["scpi"]["nom"], "scpi_id": r["scpi"]["scpi_id"],
         "td": r["ind"]["td"], "ecart": r["ind"]["ecart"], "tof": r["ind"]["tof"],
         "capi": r["ind"]["capi"]}
        for r in rows
    ]
    top_td = sorted([r for r in rows if r["ind"]["td"] is not None],
                    key=lambda r: r["ind"]["td"], reverse=True)[:5]
    top_decote = sorted([r for r in rows if r["ind"]["ecart"] is not None],
                        key=lambda r: r["ind"]["ecart"])[:5]
    return _TEMPLATES.TemplateResponse(request, "dashboard.html", {
        "rows": rows, "kpis": kpis, "cols": SCREENER,
        "chart_data": chart_data, "top_td": top_td, "top_decote": top_decote,
    })


@app.get("/comparatif", response_class=HTMLResponse)
def comparatif(request: Request, store: Store = Depends(get_store)) -> Any:
    return _TEMPLATES.TemplateResponse(request, "comparatif.html",
                                       {"rows": dataview.screener_rows(store), "cols": SCREENER})


@app.get("/scpi/{scpi_id}", response_class=HTMLResponse)
def scpi_detail(scpi_id: str, request: Request, store: Store = Depends(get_store)) -> Any:
    s = dataview.scpi_row(store, scpi_id)
    if s is None:
        return HTMLResponse(f"SCPI inconnue : {scpi_id}", status_code=404)
    metrics = []
    for key in MetricKey:
        c = dataview.current_cell(store, scpi_id, str(key))
        if c is not None:
            metrics.append({"key": str(key), "cell": c})
    av = dataview.a_verifier(store, scpi_id)
    charts = [
        {"key": str(k), "label": str(k).replace("_", " "),
         "points": dataview.history(store, scpi_id, str(k))}
        for k in _HISTORY_KEYS
    ]
    charts = [c for c in charts if c["points"]]
    return _TEMPLATES.TemplateResponse(request, "scpi.html", {
        "scpi": s, "metrics": metrics, "averifier": av, "charts": charts,
        "metric_keys": [str(k) for k in MetricKey],
    })


@app.get("/a-verifier", response_class=HTMLResponse)
def averifier_all(request: Request, store: Store = Depends(get_store)) -> Any:
    items = dataview.a_verifier(store)
    return _TEMPLATES.TemplateResponse(request, "a_verifier.html", {"items": items})


@app.get("/sources", response_class=HTMLResponse)
def sources_page(request: Request, store: Store = Depends(get_store)) -> Any:
    return _TEMPLATES.TemplateResponse(request, "sources.html",
                                       {"rows": dataview.sources(store)})


@app.get("/api/history/{scpi_id}/{metric_key}")
def api_history(scpi_id: str, metric_key: str, store: Store = Depends(get_store)) -> Any:
    return JSONResponse(dataview.history(store, scpi_id, metric_key))


@app.post("/override")
def add_override(
    scpi_id: str = Form(...),
    metric_key: str = Form(...),
    value: str = Form(...),
    period: str = Form(""),
    unit: str = Form(""),
    published_at: str = Form(""),
    source_url: str = Form(""),
    ajax: str = Form(""),
    store: Store = Depends(get_store),
) -> Any:
    num = parse_number_fr(value)
    store.add_override(
        scpi_id=scpi_id, metric_key=metric_key, period=period or None,
        value_num=num, value_text=None if num is not None else value.strip(),
        unit=unit or None, source_url=source_url or None,
        published_at=published_at or None, note="saisie via l'app web",
    )
    if ajax:
        return JSONResponse({"ok": True, "scpi_id": scpi_id, "metric_key": metric_key,
                             "value": num if num is not None else value.strip()})
    return RedirectResponse(f"/scpi/{scpi_id}", status_code=303)


def main() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
