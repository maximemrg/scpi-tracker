"""Accès lecture pour les restitutions (web, et réutilisable ailleurs).

Applique la règle de priorité : correction manuelle (override) > dernière valeur
OK > dernière A_VERIFIER (pour garder le lien source). Aucune valeur inventée.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Confidence, MetricKey, Status
from .storage import Store


@dataclass
class Cell:
    value: float | str | None
    unit: str | None
    confidence: str | None
    status: str
    source_url: str | None
    published_at: str | None
    period: str | None = None


def list_scpi(store: Store) -> list[dict[str, Any]]:
    rows = store.conn.execute("SELECT * FROM scpi ORDER BY sdg_nom, nom").fetchall()
    return [dict(r) for r in rows]


def scpi_row(store: Store, scpi_id: str) -> dict[str, Any] | None:
    r = store.conn.execute("SELECT * FROM scpi WHERE scpi_id=?", (scpi_id,)).fetchone()
    return dict(r) if r else None


def current_cell(store: Store, scpi_id: str, key: str) -> Cell | None:
    ov = store.conn.execute(
        """SELECT value_num, value_text, unit, source_url, published_at, period
           FROM manual_overrides WHERE scpi_id=? AND metric_key=?
           ORDER BY created_at DESC, id DESC LIMIT 1""",
        (scpi_id, key),
    ).fetchone()
    if ov is not None:
        return Cell(_num_or_text(ov), ov["unit"], Confidence.MANUELLE, Status.OK,
                    ov["source_url"], ov["published_at"], ov["period"])
    ok = store.conn.execute(
        """SELECT value_num, value_text, unit, confidence, source_url, published_at, period
           FROM metrics WHERE scpi_id=? AND metric_key=? AND status='OK'
           ORDER BY collected_at DESC, id DESC LIMIT 1""",
        (scpi_id, key),
    ).fetchone()
    if ok is not None:
        return Cell(_num_or_text(ok), ok["unit"], ok["confidence"], Status.OK,
                    ok["source_url"], ok["published_at"], ok["period"])
    av = store.conn.execute(
        """SELECT source_url, period FROM metrics
           WHERE scpi_id=? AND metric_key=? AND status='A_VERIFIER'
           ORDER BY collected_at DESC, id DESC LIMIT 1""",
        (scpi_id, key),
    ).fetchone()
    if av is not None:
        return Cell(None, None, Confidence.FAIBLE, Status.A_VERIFIER,
                    av["source_url"], None, av["period"])
    return None


def history(store: Store, scpi_id: str, key: str) -> list[dict[str, Any]]:
    """Série historique (valeurs OK) d'une métrique, triée par date de donnée."""
    rows = store.conn.execute(
        """SELECT period, value_num, published_at, confidence, collected_at
           FROM metrics
           WHERE scpi_id=? AND metric_key=? AND status='OK' AND value_num IS NOT NULL
           ORDER BY COALESCE(published_at, collected_at), id""",
        (scpi_id, key),
    ).fetchall()
    # + overrides manuels (confiance MANUELLE) dans la même série
    ovs = store.conn.execute(
        """SELECT period, value_num, published_at, created_at
           FROM manual_overrides WHERE scpi_id=? AND metric_key=? AND value_num IS NOT NULL
           ORDER BY COALESCE(published_at, created_at), id""",
        (scpi_id, key),
    ).fetchall()
    out = [
        {"period": r["period"], "value": r["value_num"],
         "date": r["published_at"] or r["collected_at"][:10], "confidence": r["confidence"]}
        for r in rows
    ]
    out += [
        {"period": r["period"], "value": r["value_num"],
         "date": r["published_at"] or r["created_at"][:10], "confidence": "MANUELLE"}
        for r in ovs
    ]
    out.sort(key=lambda d: str(d["date"]))
    return out


def a_verifier(store: Store, scpi_id: str | None = None) -> list[dict[str, Any]]:
    where = "AND scpi_id=?" if scpi_id else ""
    params: tuple[Any, ...] = (scpi_id,) if scpi_id else ()
    rows = store.conn.execute(
        f"""SELECT scpi_id, metric_key, period, note, source_url, MAX(collected_at) c
            FROM metrics WHERE status='A_VERIFIER' {where}
            GROUP BY scpi_id, metric_key, period
            ORDER BY scpi_id, metric_key""",
        params,
    ).fetchall()
    # Ne pas reproposer ce qui a déjà un override manuel.
    out = []
    for r in rows:
        exists = store.conn.execute(
            """SELECT 1 FROM manual_overrides
               WHERE scpi_id=? AND metric_key=? AND (period IS ? OR period=?) LIMIT 1""",
            (r["scpi_id"], r["metric_key"], r["period"], r["period"]),
        ).fetchone()
        if not exists:
            out.append(dict(r))
    return out


def sources(store: Store) -> list[dict[str, Any]]:
    rows = store.conn.execute(
        """SELECT scpi_id, metric_key, period, value_num, value_text, unit,
                  published_at, confidence, source_url, MAX(collected_at)
           FROM metrics WHERE status='OK'
           GROUP BY scpi_id, metric_key, period
           ORDER BY scpi_id, metric_key""",
    ).fetchall()
    return [dict(r) for r in rows]


# --- Indicateurs de sélection (réutilisés par l'app web et l'export HTML) -----
# (id, libellé, unité, sens favorable : haut|bas|None)
SCREENER_COLS: list[tuple[str, str, str, str | None]] = [
    ("td", "TD", "%", "haut"),
    ("tri5", "TRI 5 ans", "%", "haut"),
    ("ecart", "Écart prix/reconst.", "%", "bas"),
    ("tof", "TOF", "%", "haut"),
    ("frais", "Frais gestion", "%", "bas"),
    ("prix", "Prix souscr.", "€", None),
    ("capi", "Capitalisation", "€", None),
    ("delai", "Délai jouiss.", "mois", "bas"),
]


def num_value(store: Store, scpi_id: str, key: str) -> float | None:
    c = current_cell(store, scpi_id, key)
    if c is None or c.status != Status.OK or not isinstance(c.value, (int, float)):
        return None
    return float(c.value)


def indicators(store: Store, scpi_id: str) -> dict[str, float | None]:
    prix = num_value(store, scpi_id, MetricKey.PRIX_SOUSCRIPTION)
    reconst = num_value(store, scpi_id, MetricKey.VALEUR_RECONSTITUTION)
    ecart = round((prix - reconst) / reconst * 100, 2) if prix and reconst else None
    return {
        "td": num_value(store, scpi_id, MetricKey.TAUX_DISTRIBUTION),
        "tri5": num_value(store, scpi_id, MetricKey.TRI_5ANS),
        "tof": num_value(store, scpi_id, MetricKey.TOF),
        "ecart": ecart,
        "frais": num_value(store, scpi_id, MetricKey.FRAIS_GESTION),
        "capi": num_value(store, scpi_id, MetricKey.CAPITALISATION),
        "prix": prix,
        "delai": num_value(store, scpi_id, MetricKey.DELAI_JOUISSANCE),
    }


def screener_rows(store: Store) -> list[dict[str, Any]]:
    rows = []
    for s in list_scpi(store):
        rows.append({
            "scpi": s, "ind": indicators(store, s["scpi_id"]),
            "n_av": len(a_verifier(store, s["scpi_id"])),
        })
    return rows


def _num_or_text(row: Any) -> float | str | None:
    if row["value_num"] is not None:
        return float(row["value_num"])
    text: str | None = row["value_text"]
    return text
