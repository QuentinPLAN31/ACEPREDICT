"""
Job de synchronisation QUOTIDIEN : télécharge et ingère les derniers résultats
de matchs, recalcule l'Elo, puis recalcule le niveau de confiance
(data_confidence) de tous les joueurs. Cf. README "Synchronisation des
données" pour le schéma d'ensemble et la configuration GitHub Actions.

Usage :
    python -m scripts.sync_daily
    python -m scripts.sync_daily --season 2025   # forcer une saison précise
                                                  # (par défaut : année en cours)

Idempotent de bout en bout : ingest_csv() (scripts/ingest_sackmann.py) ne
duplique jamais un match déjà connu, donc ce script peut tourner chaque jour
sur le(s) même(s) fichier(s) — utile car le CSV de la saison en cours est mis
à jour au fil des tournois, pas republié d'un coup en fin d'année.

Source des données (IMPORTANT, changement 2026) : ce script visait à l'origine
les dépôts GitHub JeffSackmann/tennis_atp et JeffSackmann/tennis_wta. Ces deux
dépôts n'existent plus (vérifié début septembre 2026 : 404 sur les pages des
dépôts eux-mêmes, sur raw.githubusercontent.com pour toutes les branches
testées (master/main), et absents de la liste des dépôts publics de cet
utilisateur via l'API GitHub) — ce n'est donc pas une panne réseau ponctuelle
ni un problème de configuration locale, la source amont a disparu.

Remplacement ATP trouvé et vérifié compatible : Tennismylife/TML-Database
(dépôt GitHub actif, mis à jour en continu, un fichier {season}.csv par
saison à la racine, en-têtes de colonnes identiques au format Sackmann
d'origine). Deux différences mineures gérées par ingest_sackmann.py :
ID joueurs alphanumériques (ex: "B0BI") au lieu de numériques — dégradés
proprement vers sackmann_id=None plutôt que de planter l'import — et
quelques codes tourney_level non standard ("250", "500", "O") qui retombent
simplement sur la catégorie par défaut "atp_tour".

WTA : AUCUNE source de remplacement (gratuite, à jour, aussi complète) n'a
été trouvée à ce jour. Le fichier WTA reste donc indisponible ("unavailable")
tant qu'une source fiable n'est pas identifiée — cf. WTA_BASE_URL ci-dessous,
laissé en l'état par honnêteté plutôt que masqué silencieusement.

Dégradation gracieuse fichier par fichier : un fichier indisponible (404) ou
une erreur réseau ponctuelle sur UN fichier n'interrompt jamais les autres —
cf. _download_csv(). Le job se termine toujours par un code de sortie 0 tant
qu'au moins la connexion à la base a fonctionné ; les échecs de téléchargement
sont seulement loggés dans le rapport ("status": "unavailable").
"""
import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.database import SessionLocal
from app.services import data_confidence
from scripts import compute_elo_ratings
from scripts.ingest_sackmann import ingest_csv

DOWNLOAD_TIMEOUT_SECONDS = 60.0

# ATP : Tennismylife/TML-Database (cf. docstring ci-dessus) -- remplace les
# anciens dépôts JeffSackmann/tennis_atp (disparus de GitHub, vérifié 2026).
# Un seul fichier par saison à la racine du dépôt, {season}.csv.
ATP_BASE_URL = "https://raw.githubusercontent.com/Tennismylife/TML-Database/master"

# WTA : JeffSackmann/tennis_wta a disparu lui aussi, et aucune source de
# remplacement n'a été trouvée à ce jour (cf. docstring). On laisse
# volontairement cette URL et l'entrée FILE_SPECS correspondante : le
# téléchargement échouera proprement ("unavailable", cf. _download_csv) sans
# jamais interrompre le reste du job -- si une source WTA fiable est trouvée
# plus tard, il suffira de mettre cette URL à jour.
WTA_BASE_URL = "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master"

FILE_SPECS = [
    # (tour, url_de_base, patron_de_nom_de_fichier, étiquette pour les logs)
    ("atp", ATP_BASE_URL, "{season}.csv", "ATP (Tennismylife/TML-Database)"),
    ("wta", WTA_BASE_URL, "wta_matches_{season}.csv", "WTA tour (source indisponible, cf. docstring)"),
]


def _download_csv(url: str) -> Optional[Path]:
    """Télécharge l'URL vers un fichier temporaire, ou None si indisponible
    (404 — fichier pas encore publié pour cette saison —, erreur réseau,
    timeout). Jamais d'exception qui remonterait au reste du job."""
    try:
        resp = httpx.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True)
        if resp.status_code != 200:
            return None
        tmp = tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False)
        tmp.write(resp.content)
        tmp.close()
        return Path(tmp.name)
    except Exception:
        return None


def run(season: Optional[int] = None, db=None) -> dict:
    season = season or datetime.now(timezone.utc).year
    owns_session = db is None
    db = db or SessionLocal()

    report = {"season": season, "files": [], "matches_inserted": 0, "players_updated_elo": 0, "confidence_changed": 0}

    try:
        for tour, base_url, filename_pattern, label in FILE_SPECS:
            filename = filename_pattern.format(season=season)
            url = f"{base_url}/{filename}"
            path = _download_csv(url)
            if path is None:
                report["files"].append({"file": filename, "label": label, "status": "unavailable", "inserted": 0})
                continue
            try:
                inserted = ingest_csv(str(path), tour=tour, db=db)
            except Exception as exc:
                report["files"].append({"file": filename, "label": label, "status": f"error: {exc}", "inserted": 0})
                continue
            finally:
                path.unlink(missing_ok=True)
            report["files"].append({"file": filename, "label": label, "status": "ok", "inserted": inserted})
            report["matches_inserted"] += inserted

        report["players_updated_elo"] = compute_elo_ratings.run(db=db)
        report["confidence_changed"] = data_confidence.recompute_all(db)
        return report
    finally:
        if owns_session:
            db.close()


def main():
    parser = argparse.ArgumentParser(description="Sync quotidienne Sackmann -> base AcePredict")
    parser.add_argument("--season", type=int, default=None, help="Année à synchroniser (défaut : année en cours)")
    args = parser.parse_args()

    report = run(season=args.season)

    print(f"[sync_daily] Saison {report['season']} :")
    for f in report["files"]:
        print(f"  - {f['label']} ({f['file']}) : {f['status']}, {f['inserted']} match(s) inséré(s)")
    print(f"[sync_daily] Total : {report['matches_inserted']} nouveaux matchs, "
          f"{report['players_updated_elo']} joueurs recalculés (Elo), "
          f"{report['confidence_changed']} niveaux de confiance mis à jour.")


if __name__ == "__main__":
    sys.exit(main())
