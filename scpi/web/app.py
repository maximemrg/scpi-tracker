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

# Métriques affichées dans le comparatif : (clé, libellé, unité)
DISPLAY: list[tuple[str, str, str]] = [
    (MetricKey.TAUX_DISTRIBUTION, "TD", "%"),
    (MetricKey.TRI_5ANS, "TRI 5 ans", "%"),
    (MetricKey.TRI_10ANS, "TRI 10 ans", "%"),
    (MetricKey.TOF, "TOF", "%"),
    (MetricKey.PRIX_SOUSCRIPTION, "Prix souscr.", "€"),
    (MetricKey.PRIX_RETRAIT, "Prix retrait", "€"),
    (MetricKey.VALEUR_RECONSTITUTION, "Reconstitution", "€"),
    (MetricKey.CAPITALISATION, "Capitalisation", "€"),
    (MetricKey.NOMBRE_ASSOCIES, "Associés", ""),
    (MetricKey.NOMBRE_IMMEUBLES, "Immeubles", ""),
    (MetricKey.DELAI_JOUISSANCE, "Délai jouiss.", "mois"),
    (MetricKey.FRAIS_GESTION, "Frais gestion", "%"),
]
# Toutes les métriques d'une fiche (pour la page détail).
ALL_METRICS: list[tuple[str, str, str]] = [
    (str(k), k.replace("_", " ").capitalize(), "") for k in MetricKey
]
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
def index(request: Request, store: Store = Depends(get_store)) -> Any:
    scpis = dataview.list_scpi(store)
    rows = []
    for s in scpis:
        cells = {}
        for key, _label, _unit in DISPLAY:
            c = dataview.current_cell(store, s["scpi_id"], key)
            cells[key] = c
        rows.append({"scpi": s, "cells": cells})
    return _TEMPLATES.TemplateResponse(request, "comparatif.html", {
        "rows": rows, "display": DISPLAY,
    })


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
    store: Store = Depends(get_store),
) -> Any:
    num = parse_number_fr(value)
    store.add_override(
        scpi_id=scpi_id, metric_key=metric_key, period=period or None,
        value_num=num, value_text=None if num is not None else value.strip(),
        unit=unit or None, source_url=source_url or None,
        published_at=published_at or None, note="saisie via l'app web",
    )
    return RedirectResponse(f"/scpi/{scpi_id}", status_code=303)


def main() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":  # pragma: no cover
    main()
