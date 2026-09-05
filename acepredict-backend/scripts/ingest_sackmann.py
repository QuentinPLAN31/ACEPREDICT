"""
Ingestion d'un (ou plusieurs) CSV au format Jeff Sackmann (tennis_atp /
tennis_wta — colonnes winner_id, loser_id, tourney_name, surface, score...)
vers les tables players / competitions / matches. Idempotent (cf.
ingest_csv) : ré-ingérer le même fichier ne duplique jamais un match déjà
connu, ce qui permet de l'appeler chaque jour sur un CSV qui grossit en
cours de saison.

Usage direct (un seul fichier) :
    python -m scripts.ingest_sackmann data/sample/atp_matches_sample.csv --tour atp

En pratique, préférer scripts/sync_daily.py qui télécharge et ingère
automatiquement le(s) fichier(s) pertinent(s) de l'année en cours, chaque
jour — cf. README "Synchronisation des données".

Note (2026) : les dépôts GitHub originaux JeffSackmann/tennis_atp et
JeffSackmann/tennis_wta n'existent plus (vérifié : 404 sur le dépôt lui-même
et sur toutes les branches). sync_daily.py utilise désormais
Tennismylife/TML-Database comme source ATP de remplacement (même schéma de
colonnes, ID joueurs alphanumériques -- cf. get_or_create_player ci-dessous).
Pour un import manuel ponctuel d'une année précise :
    git clone https://github.com/Tennismylife/TML-Database.git
    python -m scripts.ingest_sackmann TML-Database/2024.csv --tour atp
Aucune source WTA de remplacement équivalente (live, à jour) n'a été trouvée
à ce jour -- cf. sync_daily.py.
"""
import argparse
import csv
import sys
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app import models

LEVEL_TO_CATEGORY = {
    "G": "grand_slam",
    "M": "masters_1000",
    "A": "atp_tour",
    "F": "finals",
    "D": "davis_cup",
}

SURFACE_MAP = {"Hard": "hard", "Clay": "clay", "Grass": "grass", "Carpet": "carpet"}


def get_or_create_player(db: Session, sackmann_id: str, name: str, hand: str,
                          country: str, height: str, tour: str) -> models.Player:
    # sackmann_id est un Integer en base (cf. models.Player) : les CSV Jeff
    # Sackmann originaux utilisaient des ID numériques, mais la source de
    # remplacement Tennismylife/TML-Database (cf. sync_daily.py) utilise des
    # ID alphanumériques (ex: "B0BI"). On dégrade proprement vers None plutôt
    # que de planter tout l'import -- le lookup par nom juste en dessous sert
    # alors de repli, comme il le fait déjà pour toute ligne sans ID.
    try:
        sid = int(sackmann_id) if sackmann_id else None
    except ValueError:
        sid = None
    player = None
    if sid:
        player = db.query(models.Player).filter(models.Player.sackmann_id == sid).first()
    if not player:
        player = db.query(models.Player).filter(models.Player.name == name).first()

    if not player:
        try:
            height_cm = int(float(height)) if height else None
        except ValueError:
            height_cm = None
        player = models.Player(
            sackmann_id=sid,
            name=name,
            hand=hand or None,
            country=country or None,
            height_cm=height_cm,
            tour=tour,
        )
        db.add(player)
        db.flush()
    return player


def get_or_create_competition(db: Session, tourney_name: str, surface: str,
                               level: str, season: int, tour: str) -> models.Competition:
    comp = (
        db.query(models.Competition)
        .filter(
            models.Competition.name == tourney_name,
            models.Competition.season == season,
            models.Competition.tour == tour,
        )
        .first()
    )
    if not comp:
        comp = models.Competition(
            name=tourney_name,
            category=LEVEL_TO_CATEGORY.get(level, "atp_tour"),
            tour=tour,
            surface=SURFACE_MAP.get(surface),
            season=season,
        )
        db.add(comp)
        db.flush()
    return comp


def _match_already_ingested(db: Session, competition_id: str, winner_id: str, loser_id: str,
                             tourney_date, round_: str) -> bool:
    """Deux joueurs ne rejouent pas le même tour d'un même tournoi le même
    jour : (compétition, vainqueur, perdant, date, tour) identifie un match
    de façon fiable, sans dépendre de match_num (pas importé, cf. en-tête).
    Nécessaire pour que scripts/sync_daily.py puisse ré-ingérer chaque jour
    le CSV de la saison en cours (qui grossit au fil des tournois) sans
    dupliquer les matchs déjà connus."""
    return (
        db.query(models.Match.id)
        .filter(
            models.Match.competition_id == competition_id,
            models.Match.winner_id == winner_id,
            models.Match.player2_id == loser_id,
            models.Match.tourney_date == tourney_date,
            models.Match.round == round_,
        )
        .first()
        is not None
    )


def ingest_csv(path: str, tour: str = "atp", db: Session | None = None) -> int:
    """Importe le CSV et renvoie le nombre de matchs NOUVELLEMENT insérés
    (idempotent : un match déjà en base — même compétition/vainqueur/
    perdant/date/tour — est silencieusement sauté, jamais dupliqué)."""
    owns_session = db is None
    db = db or SessionLocal()
    count = 0
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tdate_raw = row.get("tourney_date", "")
                try:
                    tdate = datetime.strptime(tdate_raw, "%Y%m%d") if tdate_raw else None
                except ValueError:
                    tdate = None
                season = tdate.year if tdate else None

                winner = get_or_create_player(
                    db, row.get("winner_id"), row["winner_name"], row.get("winner_hand"),
                    row.get("winner_ioc"), row.get("winner_ht"), tour,
                )
                loser = get_or_create_player(
                    db, row.get("loser_id"), row["loser_name"], row.get("loser_hand"),
                    row.get("loser_ioc"), row.get("loser_ht"), tour,
                )
                comp = get_or_create_competition(
                    db, row["tourney_name"], row.get("surface", ""),
                    row.get("tourney_level", "A"), season, tour,
                )

                round_ = row.get("round")
                if _match_already_ingested(db, comp.id, winner.id, loser.id, tdate, round_):
                    continue

                surface = SURFACE_MAP.get(row.get("surface", ""))
                match = models.Match(
                    competition_id=comp.id,
                    tourney_date=tdate,
                    round=round_,
                    surface=surface,
                    player1_id=winner.id,
                    player2_id=loser.id,
                    winner_id=winner.id,
                    score=row.get("score"),
                    stats={
                        "w_ace": row.get("w_ace"), "w_df": row.get("w_df"),
                        "l_ace": row.get("l_ace"), "l_df": row.get("l_df"),
                        "winner_rank": row.get("winner_rank"), "loser_rank": row.get("loser_rank"),
                    },
                    source="sackmann",
                )
                db.add(match)
                db.flush()  # rend le match visible à _match_already_ingested pour la suite du même fichier
                count += 1

        db.commit()
        return count
    finally:
        if owns_session:
            db.close()


def main():
    parser = argparse.ArgumentParser(description="Ingestion CSV Jeff Sackmann -> base AcePredict")
    parser.add_argument("csv_path", help="Chemin vers le fichier atp_matches_YYYY.csv (ou échantillon)")
    parser.add_argument("--tour", choices=["atp", "wta"], default="atp")
    args = parser.parse_args()

    n = ingest_csv(args.csv_path, tour=args.tour)
    print(f"{n} matchs importés depuis {args.csv_path}")


if __name__ == "__main__":
    sys.exit(main())
