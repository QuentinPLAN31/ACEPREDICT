# A lancer via railway ssh: PYTHONPATH=/app python3 -m scripts.check_player_tour_field
#
# check_rankings_coverage.py a montre des joueuses WTA (Karolina Muchova,
# Victoria Mboko, Amanda Anisimova, Belinda Bencic...) apparaissant dans une
# requete filtree Player.tour == TourEnum.atp -- ce script affiche la
# valeur BRUTE de la colonne 'tour' (et son type Python exact) pour
# quelques-unes de ces joueuses, pour savoir si tour='atp' est vraiment
# stocke en base (bug de creation) ou si c'est le FILTRE qui est en cause.
from app import models
from app.database import SessionLocal

NAMES = ["Muchova", "Mboko", "Anisimova", "Bencic", "Shnaider", "Eala", "Alexandrova", "Mertens", "Chwalinska", "Paolini", "Dabrowski", "Cirstea"]


def main():
    db = SessionLocal()
    try:
        for n in NAMES:
            rows = db.query(models.Player).filter(models.Player.name.ilike(f"%{n}%")).all()
            for p in rows:
                print(f"name={p.name!r:35} tour_repr={p.tour!r:25} tour_value={getattr(p.tour, 'value', p.tour)!r} type={type(p.tour)} rank={p.current_rank} id={p.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
