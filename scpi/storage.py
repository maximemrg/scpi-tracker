"""Stockage SQLite APPEND-ONLY.

On n'écrase JAMAIS une ligne de `metrics` : chaque collecte ajoute des lignes.
L'historique EST le produit. Les corrections manuelles vivent dans
`manual_overrides` et gagnent toujours sur le scraping au moment de la lecture.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

from .models import Metric, now_utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS scpi (
    scpi_id    TEXT PRIMARY KEY,
    nom        TEXT NOT NULL,
    sdg_key    TEXT NOT NULL,
    sdg_nom    TEXT NOT NULL,
    domaine    TEXT
);

-- APPEND-ONLY. Aucune UPDATE/DELETE dans le code applicatif.
CREATE TABLE IF NOT EXISTS metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scpi_id      TEXT NOT NULL,
    metric_key   TEXT NOT NULL,
    value_num    REAL,
    value_text   TEXT,
    unit         TEXT,
    period       TEXT,
    source_url   TEXT NOT NULL,
    published_at TEXT,          -- date de la donnée (ISO), pas de la collecte
    collected_at TEXT NOT NULL, -- horodatage de collecte (ISO)
    confidence   TEXT NOT NULL,
    status       TEXT NOT NULL,
    raw          TEXT,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_lookup
    ON metrics (scpi_id, metric_key, period, collected_at);

-- Corrections manuelles : prioritaires et conservées.
CREATE TABLE IF NOT EXISTS manual_overrides (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scpi_id      TEXT NOT NULL,
    metric_key   TEXT NOT NULL,
    period       TEXT,
    value_num    REAL,
    value_text   TEXT,
    unit         TEXT,
    source_url   TEXT,
    published_at TEXT,
    note         TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_override_lookup
    ON manual_overrides (scpi_id, metric_key, period, created_at);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scpi_id     TEXT NOT NULL,
    metric_key  TEXT NOT NULL,
    period      TEXT,
    old_value   TEXT,
    new_value   TEXT,
    message     TEXT NOT NULL,
    detected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    ok_count        INTEGER DEFAULT 0,
    averifier_count INTEGER DEFAULT 0,
    error_count     INTEGER DEFAULT 0,
    summary         TEXT
);
"""


class Store:
    def __init__(self, path: Path | str = "data/scpi.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- Dimension SCPI -------------------------------------------------------
    def upsert_scpi(
        self, scpi_id: str, nom: str, sdg_key: str, sdg_nom: str, domaine: str
    ) -> None:
        self.conn.execute(
            """INSERT INTO scpi (scpi_id, nom, sdg_key, sdg_nom, domaine)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(scpi_id) DO UPDATE SET
                 nom=excluded.nom, sdg_key=excluded.sdg_key,
                 sdg_nom=excluded.sdg_nom, domaine=excluded.domaine""",
            (scpi_id, nom, sdg_key, sdg_nom, domaine),
        )
        self.conn.commit()

    # -- Écriture append-only -------------------------------------------------
    def insert_metrics(self, metrics: Iterable[Metric]) -> int:
        rows = [
            (
                m.scpi_id, m.metric_key, m.value_num, m.value_text, m.unit, m.period,
                m.source_url,
                m.published_at.isoformat() if m.published_at else None,
                m.collected_at.isoformat(),
                str(m.confidence), str(m.status), m.raw, m.note,
            )
            for m in metrics
        ]
        self.conn.executemany(
            """INSERT INTO metrics
               (scpi_id, metric_key, value_num, value_text, unit, period,
                source_url, published_at, collected_at, confidence, status, raw, note)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self.conn.commit()
        return len(rows)

    # -- Lecture : override manuel prioritaire, sinon dernière valeur scrapée --
    def latest_value(
        self, scpi_id: str, metric_key: str, period: str | None = None
    ) -> sqlite3.Row | None:
        ov = self._latest_override(scpi_id, metric_key, period)
        if ov is not None:
            return ov
        clause = "AND period = ?" if period is not None else ""
        params: list[object] = [scpi_id, metric_key]
        if period is not None:
            params.append(period)
        row: sqlite3.Row | None = self.conn.execute(
            f"""SELECT * FROM metrics
                WHERE scpi_id = ? AND metric_key = ? {clause}
                  AND status = 'OK'
                ORDER BY collected_at DESC, id DESC LIMIT 1""",
            params,
        ).fetchone()
        return row

    def _latest_override(
        self, scpi_id: str, metric_key: str, period: str | None
    ) -> sqlite3.Row | None:
        clause = "AND period = ?" if period is not None else ""
        params: list[object] = [scpi_id, metric_key]
        if period is not None:
            params.append(period)
        row: sqlite3.Row | None = self.conn.execute(
            f"""SELECT *, 'MANUELLE' AS confidence, 'OK' AS status
                FROM manual_overrides
                WHERE scpi_id = ? AND metric_key = ? {clause}
                ORDER BY created_at DESC, id DESC LIMIT 1""",
            params,
        ).fetchone()
        return row

    # -- Détection de changement ---------------------------------------------
    def detect_change(self, m: Metric) -> tuple[float | None, float] | None:
        """Retourne (ancienne_valeur, nouvelle_valeur) si la valeur numérique a
        changé vs la dernière valeur OK connue (même période), sinon None."""
        if m.status != "OK" or m.value_num is None:
            return None
        prev = self.conn.execute(
            """SELECT value_num FROM metrics
               WHERE scpi_id=? AND metric_key=? AND status='OK' AND value_num IS NOT NULL
                 AND (period IS ? OR period = ?)
               ORDER BY collected_at DESC, id DESC LIMIT 1""",
            (m.scpi_id, m.metric_key, m.period, m.period),
        ).fetchone()
        if prev is None:
            return None
        old = prev["value_num"]
        if old != m.value_num:
            return old, m.value_num
        return None

    def record_alert(
        self, scpi_id: str, metric_key: str, period: str | None,
        old_value: object, new_value: object, message: str,
    ) -> None:
        self.conn.execute(
            """INSERT INTO alerts
               (scpi_id, metric_key, period, old_value, new_value, message, detected_at)
               VALUES (?,?,?,?,?,?,?)""",
            (scpi_id, metric_key, period, str(old_value), str(new_value),
             message, now_utc().isoformat()),
        )
        self.conn.commit()

    # -- Runs -----------------------------------------------------------------
    def start_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at) VALUES (?)", (now_utc().isoformat(),)
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def finish_run(
        self, run_id: int, ok: int, averifier: int, errors: int, summary: str
    ) -> None:
        self.conn.execute(
            """UPDATE runs SET finished_at=?, ok_count=?, averifier_count=?,
               error_count=?, summary=? WHERE id=?""",
            (now_utc().isoformat(), ok, averifier, errors, summary, run_id),
        )
        self.conn.commit()

    def add_override(
        self, *, scpi_id: str, metric_key: str, period: str | None,
        value_num: float | None = None, value_text: str | None = None,
        unit: str | None = None, source_url: str | None = None,
        published_at: str | None = None, note: str | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO manual_overrides
               (scpi_id, metric_key, period, value_num, value_text, unit,
                source_url, published_at, note, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (scpi_id, metric_key, period, value_num, value_text, unit,
             source_url, published_at, note, now_utc().isoformat()),
        )
        self.conn.commit()


def persist_run(
    store: Store, metrics: Sequence[Metric], *, started: datetime | None = None
) -> tuple[int, int, list[str]]:
    """Insère les métriques d'un run, émet les alertes de changement.

    Retourne (nb_ok, nb_a_verifier, lignes_d_alerte).
    """
    _ = started
    alerts: list[str] = []
    for m in metrics:
        change = store.detect_change(m)
        if change is not None:
            old, new = change
            msg = f"{m.scpi_id}/{m.metric_key} ({m.period}): {old} -> {new}"
            store.record_alert(m.scpi_id, m.metric_key, m.period, old, new, msg)
            alerts.append(msg)
    store.insert_metrics(metrics)
    ok = sum(1 for m in metrics if m.status == "OK")
    av = sum(1 for m in metrics if m.status == "A_VERIFIER")
    return ok, av, alerts
