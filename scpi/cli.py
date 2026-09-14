"""Orchestrateur en ligne de commande.

Usage :
  python -m scpi.cli collect <scpi_id>     # collecte une SCPI
  python -m scpi.cli collect --sdg corum_lepargne
  python -m scpi.cli list                  # liste les SCPI du registry
"""

from __future__ import annotations

import argparse
import sys

from .http import PoliteClient
from .models import now_utc
from .registry import Registry, ScpiEntry, load_registry
from .sources import ADAPTERS
from .storage import Store, persist_run


def _client(reg: Registry) -> PoliteClient:
    pol = reg.collecte
    return PoliteClient(
        user_agent=pol.get("user_agent", "SCPI-Tracker/0.1"),
        min_delay=float(pol.get("delai_min_secondes", 2)),
        blocked_domains=tuple(reg.blocked_domains),
        cache_dir=".http_cache",
    )


def _collect_entry(reg: Registry, client: PoliteClient, store: Store, entry: ScpiEntry) -> None:
    adapter_cls = ADAPTERS.get(entry.sdg_key)
    if adapter_cls is None:
        print(f"  [SKIP] {entry.scpi_id}: pas d'adaptateur pour {entry.sdg_key}")
        return
    store.upsert_scpi(entry.scpi_id, entry.nom, entry.sdg_key, entry.sdg_nom, entry.domaine)
    adapter = adapter_cls(client, collected_at=now_utc())
    metrics = adapter.fetch_metrics(entry)
    ok, av, alerts = persist_run(store, metrics)
    print(f"  {entry.scpi_id}: {ok} OK, {av} A_VERIFIER, {len(alerts)} alerte(s)")
    for m in metrics:
        if m.status == "A_VERIFIER":
            print(f"      A_VERIFIER {m.metric_key}: {m.note}")


def cmd_collect(args: argparse.Namespace) -> int:
    reg = load_registry()
    client = _client(reg)
    with Store(args.db) as store:
        run_id = store.start_run()
        if args.all:
            entries = [e for e in reg.entries.values() if e.sdg_key in ADAPTERS]
        elif args.sdg:
            entries = reg.by_sdg(args.sdg)
        elif args.scpi_id:
            entry = reg.entries.get(args.scpi_id)
            if entry is None:
                print(f"SCPI inconnue: {args.scpi_id}", file=sys.stderr)
                return 2
            entries = [entry]
        else:
            print("Préciser un <scpi_id>, --sdg ou --all", file=sys.stderr)
            return 2
        total_ok = total_av = 0
        for entry in entries:
            print(f"- {entry.nom} ({entry.scpi_id})")
            _collect_entry(reg, client, store, entry)
        store.finish_run(run_id, total_ok, total_av, 0, f"{len(entries)} SCPI")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    reg = load_registry()
    for e in reg.entries.values():
        flag = "" if e.sdg_key in ADAPTERS else "  (pas d'adaptateur)"
        print(f"{e.scpi_id:26} {e.sdg_key:22} {e.nom}{flag}")
    return 0


def cmd_template(args: argparse.Namespace) -> int:
    from .manual import generate_template
    with Store(args.db) as store:
        n = generate_template(store, args.out)
    print(f"{n} entrée(s) à saisir écrites dans {args.out}")
    return 0


def cmd_import_overrides(args: argparse.Namespace) -> int:
    from .manual import import_template
    with Store(args.db) as store:
        n = import_template(store, args.file)
    print(f"{n} correction(s) manuelle(s) importée(s) depuis {args.file}")
    return 0


def cmd_excel(args: argparse.Namespace) -> int:
    from .excel import build_workbook
    reg = load_registry()
    with Store(args.db) as store:
        build_workbook(store, args.out, reg)
    print(f"Classeur écrit : {args.out}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    """Résumé Markdown du dernier run (pour le step summary de la CI)."""
    with Store(args.db) as store:
        run = store.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        ok = store.conn.execute("SELECT COUNT(*) c FROM metrics WHERE status='OK'").fetchone()["c"]
        av = store.conn.execute(
            "SELECT COUNT(*) c FROM metrics WHERE status='A_VERIFIER'").fetchone()["c"]
        n_scpi = store.conn.execute("SELECT COUNT(*) c FROM scpi").fetchone()["c"]
        alerts = store.conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT 50").fetchall()
        zero = store.conn.execute(
            """SELECT s.nom FROM scpi s
               WHERE NOT EXISTS (SELECT 1 FROM metrics m
                                 WHERE m.scpi_id=s.scpi_id AND m.status='OK')
               ORDER BY s.nom"""
        ).fetchall()

    lines = ["# Collecte SCPI", ""]
    if run:
        lines.append(f"- Run démarré : {run['started_at']}")
    lines += [
        f"- SCPI en base : **{n_scpi}**",
        f"- Métriques OK : **{ok}** · À vérifier : **{av}**",
        "",
        "## Changements détectés (prix / TD)",
    ]
    if alerts:
        lines += [f"- {a['message']}" for a in alerts]
    else:
        lines.append("- Aucun changement vs dernière valeur connue.")
    lines += ["", "## SCPI sans aucune métrique fiable (à investiguer)"]
    lines += [f"- {z['nom']}" for z in zero] or ["- (aucune)"]
    print("\n".join(lines))
    return 0


def cmd_push_sheets(args: argparse.Namespace) -> int:
    """Push optionnel vers Google Sheets (derrière un flag). No-op si non configuré."""
    from .sheets import push_to_sheets
    return push_to_sheets(args.db)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scpi")
    parser.add_argument("--db", default="data/scpi.sqlite")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="collecte une ou plusieurs SCPI")
    c.add_argument("scpi_id", nargs="?")
    c.add_argument("--sdg", help="collecte toutes les SCPI d'une société de gestion")
    c.add_argument("--all", action="store_true", help="collecte toutes les SCPI (tous adaptateurs)")
    c.set_defaults(func=cmd_collect)

    ls = sub.add_parser("list", help="liste les SCPI du registry")
    ls.set_defaults(func=cmd_list)

    tp = sub.add_parser("template", help="génère le gabarit de saisie manuelle (A_VERIFIER)")
    tp.add_argument("--out", default="saisie_manuelle.yaml")
    tp.set_defaults(func=cmd_template)

    im = sub.add_parser("import-overrides", help="importe un gabarit complété (manual_overrides)")
    im.add_argument("file")
    im.set_defaults(func=cmd_import_overrides)

    ex = sub.add_parser("excel", help="génère SCPI_tracker.xlsx")
    ex.add_argument("--out", default="SCPI_tracker.xlsx")
    ex.set_defaults(func=cmd_excel)

    sm = sub.add_parser("summary", help="résumé Markdown du dernier run (CI)")
    sm.set_defaults(func=cmd_summary)

    ps = sub.add_parser("push-sheets", help="push Google Sheets (si configuré)")
    ps.set_defaults(func=cmd_push_sheets)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
