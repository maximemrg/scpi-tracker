# SCPI Tracker

Collecte, historise et restitue dans un tableur les paramètres clés de 26 SCPI,
à partir de **sources primaires uniquement** (sites et bulletins des sociétés de
gestion), et calcule la performance réelle d'un portefeuille personnel.

## Principe : fiabilité avant exhaustivité

Règle absolue : **aucune donnée n'est inventée, interpolée ou « estimée »**.
Chaque valeur stockée porte : `source_url`, `date_publication` (date de la
donnée), `date_collecte`, et une `confiance` :

| Confiance | Sens |
|---|---|
| `HAUTE` | parsée d'un bulletin / d'une page officielle de la société de gestion |
| `MOYENNE` | page officielle mais structure ambiguë |
| `FAIBLE` | extraction incertaine |
| `MANUELLE` | saisie à la main (prioritaire sur le scraping) |

Si un chiffre ne peut pas être extrait de façon certaine → valeur `NULL`, statut
`A_VERIFIER`, lien vers la page. **Jamais** de valeur par défaut, jamais de
reprise de l'ancienne valeur en la faisant passer pour fraîche.

Sources : **uniquement les sociétés de gestion** et documents réglementaires.
Les agrégateurs commerciaux (MeilleureSCPI, France SCPI, Louve Invest…) sont
bloqués (liste `meta.sources_interdites` du registry). Collecte polie :
`robots.txt` respecté, 1 requête / 2 s par domaine, User-Agent explicite.

## Installation

```bash
make install        # crée .venv et installe le projet + outils de dev
```

Python 3.11+ requis. (Compatible `uv` : `uv pip install -e ".[dev]"`.)

## Utilisation

```bash
make check                              # ruff + mypy + pytest
python -m scpi.cli list                 # liste les 26 SCPI et leur adaptateur
python -m scpi.cli collect --all        # collecte toutes les SCPI
python -m scpi.cli collect --sdg corum_lepargne
python -m scpi.cli collect corum_eurion # une seule SCPI
python -m scpi.cli excel                # génère SCPI_tracker.xlsx
python -m scpi.cli summary              # résumé Markdown du dernier run
```

La base `data/scpi.sqlite` et `SCPI_tracker.xlsx` sont **versionnés** :
l'historique est le produit.

## Architecture

```
scpi/
  models.py       Metric (confiance, statut), clés de métriques
  parsing.py      formats FR (nombres « 1 234,56 € », %, dates, trimestres)
  storage.py      SQLite APPEND-ONLY : metrics / manual_overrides / alerts / runs
  http.py         client poli (robots.txt, throttling, blocklist, cache)
  pdf.py          pdfplumber : texte + tableaux + mots positionnés
  registry.py     lecture de sources/registry.yaml
  sources/        UN adaptateur par société de gestion (pas de parser universel)
  manual.py       gabarit de saisie <-> manual_overrides
  portfolio.py    PRU, +/- value, dividendes, TRI réel (XIRR)
  excel.py        génération du classeur formaté
  sheets.py       push Google Sheets optionnel
  cli.py          orchestrateur
```

Le stockage est **append-only** : chaque collecte ajoute des lignes, on n'écrase
jamais. Une correction manuelle (`manual_overrides`) gagne toujours sur le
scraping. Un changement de prix ou de TD écrit une ligne dans `alerts`.

Beaucoup de bulletins sont des plaquettes peu lisibles par machine (PDF image,
polices vectorisées, grilles HTML). D'où une stratégie **hybride** : on
automatise le lisible, et le reste passe par la saisie manuelle (voir plus bas).
Heuristique : pour chaque société de gestion, on regarde d'abord le **site HTML**
(souvent des KPI structurés) avant de s'attaquer aux PDF.

## Comment ajouter une SCPI

Éditer `sources/registry.yaml`, sous la bonne société de gestion :

```yaml
societes_gestion:
  ma_sdg:
    nom: "Ma Société de Gestion"
    domaine: "exemple.fr"
    strategie_bulletin: html_site        # ou scrape_listing
    scpi:
      ma_scpi:
        nom: "Ma SCPI"
        fiche_url: "https://www.exemple.fr/scpi/ma-scpi"
        documents_url: "https://www.exemple.fr/scpi/ma-scpi"
        verifie: false                    # true une fois l'URL réellement ouverte
```

Le `scpi_id` (clé) sert d'identifiant partout (base, portefeuille, Excel).

## Comment ajouter une source (adaptateur)

Un adaptateur = une société de gestion. Créer `scpi/sources/ma_sdg.py` :

```python
from ..models import Confidence, Metric, MetricKey
from ..registry import ScpiEntry
from .base import SourceAdapter

class MaSdgAdapter(SourceAdapter):
    sdg_key = "ma_sdg"                     # doit correspondre à la clé du registry

    def fetch_metrics(self, entry: ScpiEntry) -> list[Metric]:
        html = self.client.get_text(entry.fiche_url)
        # ... extraire de façon SÛRE ; sinon Metric.a_verifier(...)
        return [...]
```

Puis l'enregistrer dans `scpi/sources/__init__.py` (dict `ADAPTERS`). Ajouter
des **fixtures figées** dans `tests/fixtures/` (HTML/texte/PDF réels) et un test
qui vérifie les valeurs exactes — c'est ce qui détecte les changements de format.

Principe de l'extraction : on ne retient que ce qui est **sans ambiguïté**
(libellé collé à sa valeur, phrase auto-portante, cellule de tableau). En cas de
doute (grille scramblée, chiffre voisin, unité incertaine) → `A_VERIFIER`.

## Comment corriger une donnée à la main

```bash
python -m scpi.cli template                        # écrit saisie_manuelle.yaml
#   -> compléter le champ `value` des lignes voulues (le lien source est fourni)
python -m scpi.cli import-overrides saisie_manuelle.yaml
```

Les valeurs saisies vont dans `manual_overrides` (confiance `MANUELLE`) et
priment sur toute collecte automatique, dans la base comme dans l'Excel.

## Mon portefeuille

Copier le gabarit puis le remplir (le vrai fichier est privé, non versionné) :

```bash
cp portefeuille.example.yaml portefeuille.yaml
```

Le système calcule alors, par ligne et en agrégé : montant investi, PRU, valeur
courante, +/- value latente, dividendes encaissés (délai de jouissance
appliqué), rendement sur prix de revient, et **TRI réel (XIRR)** sur les flux
datés. Il distingue le rendement affiché par la société de gestion (TD sur prix
moyen) de **votre** rendement sur prix de revient. Les lignes en nue-propriété
sont signalées (valorisation nécessitant une clé de démembrement).

## Le classeur `SCPI_tracker.xlsx`

Onglets : **Dashboard** (portefeuille + couverture + graphique TD),
**Comparatif** (une ligne par SCPI, filtres, mise en forme conditionnelle),
**Portefeuille**, **Historique**, **Flux**, **Sources**, **A_VERIFIER**.
Chaque cellule de donnée porte un commentaire (source + date + confiance) ;
les cellules `FAIBLE` sont en orange, les cases en échec affichent « À VÉRIFIER »
avec le lien.

## Automatisation (CI)

`.github/workflows/scpi.yml` : cron **lundi 7h UTC** + déclenchement manuel.
Le job : `make check` → `collect --all` → `excel` → résumé Markdown dans le step
summary → commit de la base et du classeur.

Push **Google Sheets** optionnel, derrière un flag (aucune clé en dur) :
- variable de dépôt `ENABLE_GSHEETS = true` et `SCPI_GSHEET_ID` ;
- secret `GCP_SERVICE_ACCOUNT_JSON` (JSON du service account).

## État de la couverture

12 sociétés de gestion, 25/26 SCPI collectées automatiquement (Swiss Life ESG
Pierre Capitale = saisie manuelle, le site bloque les clients non-navigateur).
Restent en `A_VERIFIER` par nature de la source : Corum Origin/XL (bulletins
**image**), Immorente / Sofidy Europe Invest (KPI en **police vectorisée**),
Kyaneos Denormandie 5 (SCPI fiscale, fiche à confirmer). Ces cases sont listées
dans l'onglet A_VERIFIER et le gabarit de saisie.
