"""Portefeuille personnel : chargement + calculs (PRU, +/- value, TRI réel).

Sépare le rendement AFFICHÉ par la société de gestion (TD sur prix moyen) de
MON rendement sur prix de revient. Aucune donnée inventée : si une brique
manque (prix courant, acomptes...), le résultat correspondant est None et
signalé, jamais estimé.

Démembrement : pour une ligne en nue-propriété, aucun dividende n'est perçu
pendant le démembrement et la valorisation exige une clé de répartition non
présente ici -> valeur courante / TRI laissés à None avec une note.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from dateutil.relativedelta import relativedelta

from .models import MetricKey
from .storage import Store

DEFAULT_PORTFOLIO_PATH = Path(__file__).resolve().parent.parent / "portefeuille.yaml"


@dataclass(frozen=True)
class Ligne:
    scpi_id: str
    date_achat: date
    nb_parts: float
    prix_unitaire: float
    frais: float = 0.0
    propriete: str = "pleine"          # "pleine" | "nue"
    demembrement_annees: int | None = None
    support: str = "direct"            # "direct" | "AV" | "SCI"

    @property
    def montant_investi(self) -> float:
        return self.nb_parts * self.prix_unitaire + self.frais

    @property
    def pru(self) -> float:
        return self.montant_investi / self.nb_parts if self.nb_parts else 0.0


@dataclass
class ResultatLigne:
    ligne: Ligne
    montant_investi: float
    pru: float
    prix_courant: float | None
    base_prix: str | None                       # "prix_retrait" | "prix_souscription"
    valeur_courante: float | None
    pv_latente: float | None
    dividendes_encaisses: float
    rendement_sur_cout: float | None            # % annualisé approx
    tri: float | None                           # XIRR
    flux: list[tuple[date, float]] = field(default_factory=list)  # achat + dividendes
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ chargement
def load_portfolio(path: Path | str | None = None) -> list[Ligne]:
    path = Path(path) if path else DEFAULT_PORTFOLIO_PATH
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    lignes: list[Ligne] = []
    for item in data.get("lignes", []):
        lignes.append(Ligne(
            scpi_id=item["scpi"],
            date_achat=_as_date(item["date"]),
            nb_parts=float(item["nb_parts"]),
            prix_unitaire=float(item["prix_unitaire"]),
            frais=float(item.get("frais", 0) or 0),
            propriete=item.get("propriete", "pleine"),
            demembrement_annees=item.get("duree_demembrement"),
            support=item.get("support", "direct"),
        ))
    return lignes


def _as_date(v: Any) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


# --------------------------------------------------------------------- XIRR
def xirr(flows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    """Taux de rendement interne sur flux datés (convention Actual/365).

    Newton-Raphson avec repli par bissection. None si pas de convergence ou si
    les flux n'ont pas au moins un montant négatif et un positif.
    """
    if len(flows) < 2:
        return None
    if not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    t0 = min(d for d, _ in flows)
    years = [(d - t0).days / 365.0 for d, _ in flows]
    amounts = [a for _, a in flows]

    def npv(rate: float) -> float:
        return float(sum(a / (1.0 + rate) ** y for a, y in zip(amounts, years, strict=True)))

    # Newton
    rate = guess
    for _ in range(100):
        f = npv(rate)
        # dérivée numérique
        h = 1e-6
        d = (npv(rate + h) - f) / h
        if d == 0:
            break
        new = rate - f / d
        if new <= -0.9999:
            new = (rate - 0.9999) / 2
        if abs(new - rate) < 1e-8:
            return new
        rate = new
    # Repli bissection sur [-0.99, 10]
    lo, hi = -0.99, 10.0
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < 1e-7:
            return mid
        if flo * fm < 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


# --------------------------------------------------------------- calcul lignes
def _latest_num(store: Store, scpi_id: str, key: str) -> float | None:
    row = store.latest_value(scpi_id, key)
    if row is None:
        return None
    v = row["value_num"]
    return float(v) if v is not None else None


def _acomptes(store: Store, scpi_id: str) -> list[tuple[date, float]]:
    """(date de versement, montant/part) des acomptes connus (OK)."""
    rows = store.conn.execute(
        """SELECT period, value_num, published_at FROM metrics
           WHERE scpi_id=? AND metric_key=? AND status='OK' AND value_num IS NOT NULL
           ORDER BY published_at""",
        (scpi_id, MetricKey.ACOMPTE),
    ).fetchall()
    out: list[tuple[date, float]] = []
    for r in rows:
        d = _as_date(r["published_at"]) if r["published_at"] else None
        if d is not None:
            out.append((d, float(r["value_num"])))
    return out


def compute_line(store: Store, ligne: Ligne, valuation: date | None = None) -> ResultatLigne:
    valuation = valuation or date.today()
    res = ResultatLigne(
        ligne=ligne, montant_investi=ligne.montant_investi, pru=ligne.pru,
        prix_courant=None, base_prix=None, valeur_courante=None, pv_latente=None,
        dividendes_encaisses=0.0, rendement_sur_cout=None, tri=None,
    )

    # Prix courant : prix de retrait (ce qu'on récupérerait), sinon souscription.
    px = _latest_num(store, ligne.scpi_id, MetricKey.PRIX_RETRAIT)
    base = "prix_retrait"
    if px is None:
        px = _latest_num(store, ligne.scpi_id, MetricKey.PRIX_SOUSCRIPTION)
        base = "prix_souscription"
    res.prix_courant = px
    res.base_prix = base if px is not None else None
    if px is None:
        res.notes.append("Prix courant inconnu (A_VERIFIER) — valeur/TRI non calculés")

    if ligne.propriete == "nue":
        res.notes.append(
            "Nue-propriété : aucun dividende pendant le démembrement ; "
            "valorisation nécessite une clé de démembrement (non calculée)"
        )
        return res

    # Valeur courante + plus/moins-value latente (pleine propriété).
    if px is not None:
        res.valeur_courante = ligne.nb_parts * px
        res.pv_latente = res.valeur_courante - ligne.montant_investi

    # Dividendes encaissés, en respectant le délai de jouissance.
    delai = _latest_num(store, ligne.scpi_id, MetricKey.DELAI_JOUISSANCE)
    jouissance = ligne.date_achat + relativedelta(months=int(delai or 0))
    flows: list[tuple[date, float]] = [(ligne.date_achat, -ligne.montant_investi)]
    total_div = 0.0
    for pay_date, montant_part in _acomptes(store, ligne.scpi_id):
        if pay_date <= ligne.date_achat or pay_date < jouissance:
            continue
        montant = montant_part * ligne.nb_parts
        total_div += montant
        flows.append((pay_date, montant))
    res.dividendes_encaisses = total_div
    res.flux = list(flows)  # achat + dividendes (sans la valeur de sortie)
    if not _acomptes(store, ligne.scpi_id):
        res.notes.append("Acomptes non collectés — dividendes/TRI partiels (voir A_VERIFIER)")

    # TRI réel (XIRR) : flux d'achat + dividendes + valeur courante à la date de valo.
    if res.valeur_courante is not None:
        res.tri = xirr([*flows, (valuation, res.valeur_courante)])

    # Rendement annualisé approx sur prix de revient (dividendes/an ÷ investi).
    annees = max((valuation - ligne.date_achat).days / 365.0, 1e-9)
    if total_div > 0:
        res.rendement_sur_cout = (total_div / annees) / ligne.montant_investi * 100

    return res


@dataclass
class Agrege:
    montant_investi: float
    valeur_courante: float
    pv_latente: float
    dividendes_encaisses: float
    tri_global: float | None
    par_sdg: dict[str, float]         # valeur courante par société de gestion


def compute_portfolio(
    store: Store, lignes: list[Ligne], valuation: date | None = None
) -> tuple[list[ResultatLigne], Agrege]:
    valuation = valuation or date.today()
    results = [compute_line(store, ligne, valuation) for ligne in lignes]

    # On n'agrège (investi / valeur / TRI) que les lignes dont la valeur courante
    # est connue, pour ne pas biaiser la +/- value (ex. nue-propriété non valorisée).
    valued = [r for r in results if r.valeur_courante is not None]
    invested = sum(r.montant_investi for r in valued)
    valeur = sum(r.valeur_courante or 0.0 for r in valued)
    divs = sum(r.dividendes_encaisses for r in valued)
    par_sdg: dict[str, float] = {}
    global_flows: list[tuple[date, float]] = []
    for r in valued:
        global_flows.extend(r.flux)  # achat + dividendes datés de la ligne
        sdg = store.conn.execute(
            "SELECT sdg_nom FROM scpi WHERE scpi_id=?", (r.ligne.scpi_id,)
        ).fetchone()
        key = sdg["sdg_nom"] if sdg else r.ligne.scpi_id
        par_sdg[key] = par_sdg.get(key, 0.0) + (r.valeur_courante or 0.0)
    if valeur:
        global_flows.append((valuation, valeur))
    agg = Agrege(
        montant_investi=invested, valeur_courante=valeur,
        pv_latente=valeur - invested, dividendes_encaisses=divs,
        tri_global=xirr(global_flows) if valeur else None, par_sdg=par_sdg,
    )
    return results, agg
