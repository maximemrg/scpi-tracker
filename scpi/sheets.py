"""Push optionnel vers Google Sheets (consultation mobile).

Activé UNIQUEMENT si configuré par variables d'environnement (aucune clé en
dur) :
  - SCPI_GSHEET_ID : identifiant du Google Sheet cible
  - GOOGLE_APPLICATION_CREDENTIALS : chemin du JSON de service account
Nécessite l'extra `sheets` (gspread, google-auth). Sinon : no-op explicite.
"""

from __future__ import annotations

import os

from .models import MetricKey
from .storage import Store

_COLS = [
    ("nom", "SCPI"),
    (MetricKey.TAUX_DISTRIBUTION, "TD %"),
    (MetricKey.TOF, "TOF %"),
    (MetricKey.PRIX_SOUSCRIPTION, "Prix souscription"),
    (MetricKey.CAPITALISATION, "Capitalisation"),
]


def push_to_sheets(db: str) -> int:
    sheet_id = os.environ.get("SCPI_GSHEET_ID")
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not sheet_id or not creds:
        print("Google Sheets désactivé (SCPI_GSHEET_ID / GOOGLE_APPLICATION_CREDENTIALS absents).")
        return 0
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("Extra 'sheets' non installé (pip install -e '.[sheets]'). Push ignoré.")
        return 0

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    gc = gspread.authorize(Credentials.from_service_account_file(creds, scopes=scopes))
    sh = gc.open_by_key(sheet_id)
    ws = sh.sheet1

    with Store(db) as store:
        scpis = store.conn.execute("SELECT * FROM scpi ORDER BY sdg_nom, nom").fetchall()
        rows: list[list[object]] = [[label for _key, label in _COLS]]
        for s in scpis:
            row: list[object] = [s["nom"]]
            for key, _label in _COLS[1:]:
                r = store.latest_value(s["scpi_id"], key)
                row.append(r["value_num"] if r and r["value_num"] is not None else "")
            rows.append(row)

    ws.clear()
    ws.update(rows, "A1")
    print(f"Google Sheets mis à jour : {len(rows) - 1} SCPI.")
    return 0
