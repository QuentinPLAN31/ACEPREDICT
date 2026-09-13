"""
Remplace le classement scrapé (tennisexplorer.com, via scripts/
sync_rankings_daily.py) par une saisie MANUELLE du classement officiel
ATP/WTA (copié-collé depuis atptour.com / wtatennis.com par l'utilisateur).
On abandonne le scraping pour cette donnée : trop fragile (structure HTML
tierce, ambiguïtés de rapprochement de noms) pour une donnée aussi
consultée. Ce script est donc désormais la SEULE source de mise à jour du
classement -- à relancer avec une liste mise à jour (éditer ATP_TOP100 /
WTA_TOP100 ci-dessous) aussi souvent que voulu.

Rapprochement : par ENSEMBLE DE MOTS du nom complet (accents retirés,
insensible à l'ordre/la casse) contre les joueurs déjà connus pour ce tour
-- fiable ici car on a le nom complet (pas juste un nom de famille comme
lors du scraping du tableau d'un tournoi). Un nom non reconnu (aucun
candidat, ou plusieurs candidats ambigus) crée une NOUVELLE fiche plutôt
que de deviner.

Usage :
    python -m scripts.apply_manual_rankings
    python -m scripts.apply_manual_rankings --dry-run
"""
import re
import sys
import unicodedata
from datetime import datetime

from app import models
from app.database import SessionLocal

# Classement ATP officiel (atptour.com), rang 1-100, saisi manuellement le
# 2026-09-13 depuis une capture d'écran fournie par l'utilisateur.
ATP_TOP100 = [
    (1, "Jannik Sinner"), (2, "Alexander Zverev"), (3, "Carlos Alcaraz"),
    (4, "Felix Auger-Aliassime"), (5, "Novak Djokovic"), (6, "Flavio Cobolli"),
    (7, "Alex de Minaur"), (8, "Daniil Medvedev"), (9, "Ben Shelton"),
    (10, "Taylor Fritz"), (11, "Arthur Fils"), (12, "Frances Tiafoe"),
    (13, "Rafael Jodar"), (14, "Lorenzo Musetti"), (15, "Learner Tien"),
    (16, "Alexander Bublik"), (17, "Brandon Nakashima"), (18, "Jakub Mensik"),
    (19, "Jiri Lehecka"), (20, "Casper Ruud"), (21, "Tommy Paul"),
    (22, "Luciano Darderi"), (23, "Valentin Vacherot"), (24, "Andrey Rublev"),
    (25, "Francisco Cerundolo"), (26, "Joao Fonseca"), (27, "Alejandro Davidovich Fokina"),
    (28, "Alejandro Tabilo"), (29, "Arthur Rinderknech"), (30, "Ignacio Buse"),
    (31, "Ugo Humbert"), (32, "Tomas Martin Etcheverry"), (33, "Arthur Fery"),
    (34, "Alexander Blockx"), (35, "Cameron Norrie"), (36, "Matteo Arnaldi"),
    (37, "Zizou Bergs"), (38, "Raphael Collignon"), (39, "Daniel Merida"),
    (40, "Luca Van Assche"), (41, "Nuno Borges"), (42, "Thiago Agustin Tirante"),
    (43, "Matteo Berrettini"), (44, "Jan-Lennard Struff"), (45, "Juan Manuel Cerundolo"),
    (46, "Alex Michelsen"), (47, "Hubert Hurkacz"), (48, "Denis Shapovalov"),
    (49, "Mariano Navone"), (50, "Karen Khachanov"), (51, "Sebastian Baez"),
    (52, "Quentin Halys"), (53, "Stefanos Tsitsipas"), (54, "Yannick Hanfmann"),
    (55, "Jaume Munar"), (56, "Tallon Griekspoor"), (57, "Daniel Altmaier"),
    (58, "Tomas Machac"), (59, "Roman Andrea Burruchaga"), (60, "Adolfo Daniel Vallejo"),
    (61, "Ethan Quinn"), (62, "Corentin Moutet"), (63, "Fabian Marozsan"),
    (64, "Miomir Kecmanovic"), (65, "Martin Landaluce"), (66, "Pablo Carreno Busta"),
    (67, "Adrian Mannarino"), (68, "Sebastian Korda"), (69, "Vit Kopriva"),
    (70, "Botic van de Zandschulp"), (71, "James Duckworth"), (72, "Jaime Faria"),
    (73, "Kamil Majchrzak"), (74, "Jenson Brooksby"), (75, "Valentin Royer"),
    (76, "Jan Choinski"), (77, "Camilo Ugo Carabelli"), (78, "Marcos Giron"),
    (79, "Hamed Medjedovic"), (80, "Zachary Svajda"), (81, "Marin Cilic"),
    (82, "Facundo Diaz Acosta"), (83, "Marco Trungelliti"), (84, "Aleksandar Kovacevic"),
    (85, "Rinky Hijikata"), (86, "Alex Molcan"), (87, "Arthur Gea"),
    (88, "Sho Shimabukuro"), (89, "Lorenzo Sonego"), (90, "Martin Damm"),
    (91, "Hugo Gaston"), (92, "Terence Atmane"), (93, "Adam Walton"),
    (94, "Coleman Wong"), (95, "Mattia Bellucci"), (96, "Aleksandar Vukic"),
    (97, "Benjamin Bonzi"), (98, "Aleksandr Shevchenko"), (99, "Roman Safiullin"),
    (100, "Jeeper de Jong"),
]

# Classement WTA officiel (wtatennis.com), rang 1-100, saisi manuellement
# le 2026-09-13 depuis le texte fourni par l'utilisateur.
WTA_TOP100 = [
    (1, "Aryna Sabalenka"), (2, "Elena Rybakina"), (3, "Jessica Pegula"),
    (4, "Coco Gauff"), (5, "Mirra Andreeva"), (6, "Linda Noskova"),
    (7, "Karolina Muchova"), (8, "Iga Swiatek"), (9, "Elina Svitolina"),
    (10, "Amanda Anisimova"), (11, "Marta Kostyuk"), (12, "Belinda Bencic"),
    (13, "Naomi Osaka"), (14, "Iva Jovic"), (15, "Victoria Mboko"),
    (16, "Diana Shnaider"), (17, "Sorana Cirstea"), (18, "Alexandra Eala"),
    (19, "Ekaterina Alexandrova"), (20, "Elise Mertens"), (21, "Jasmine Paolini"),
    (22, "Maja Chwalinska"), (23, "Anna Kalinskaya"), (24, "Madison Keys"),
    (25, "Anastasia Potapova"), (26, "Marie Bouzkova"), (27, "Emma Navarro"),
    (28, "Ann Li"), (29, "Barbora Krejcikova"), (30, "Sara Bejlek"),
    (31, "Diane Parry"), (32, "Jelena Ostapenko"), (33, "Leylah Fernandez"),
    (34, "Nikola Bartunkova"), (35, "Maria Sakkari"), (36, "Janice Tjen"),
    (37, "Hailey Baptiste"), (38, "Clara Tauson"), (39, "Donna Vekic"),
    (40, "Cristina Bucsa"), (41, "Magdalena Frech"), (42, "Katerina Siniakova"),
    (43, "Xinyu Wang"), (44, "Jaqueline Cristian"), (45, "Daria Snigur"),
    (46, "Oleksandra Oliynykova"), (47, "Liudmila Samsonova"), (48, "Tamara Korpatsch"),
    (49, "Lilli Tagger"), (50, "Tereza Valentova"), (51, "Anhelina Kalinina"),
    (52, "Mayar Sherif"), (53, "Zeynep Sonmez"), (54, "Shuai Zhang"),
    (55, "Peyton Stearns"), (56, "Viktorija Golubic"), (57, "Karolina Pliskova"),
    (58, "Yuliia Starodubtseva"), (59, "Camila Osorio"), (60, "Ashlyn Krueger"),
    (61, "Daria Kasatkina"), (62, "Katie Boulter"), (63, "Talia Gibson"),
    (64, "Elena-Gabriela Ruse"), (65, "Caty Mcnally"), (66, "Mccartney Kessler"),
    (67, "Elisabetta Cocciaretto"), (68, "Panna Udvardy"), (69, "Alina Korneeva"),
    (70, "Emma Raducanu"), (71, "Kimberly Birrell"), (72, "Maya Joint"),
    (73, "Anna Bondar"), (74, "Renata Zarazua"), (75, "Darja Vidmanova"),
    (76, "Lanlana Tararudee"), (77, "Petra Marcinko"), (78, "Katie Volynets"),
    (79, "Alycia Parks"), (80, "Xiyu Wang"), (81, "Hanne Vandewinkel"),
    (82, "Magda Linette"), (83, "Tatjana Maria"), (84, "Yulia Putintseva"),
    (85, "Antonia Ruzic"), (86, "Maria Timofeeva"), (87, "Paula Badosa"),
    (88, "Emiliana Arango"), (89, "Simona Waltert"), (90, "Sinja Kraus"),
    (91, "Solana Sierra"), (92, "Kamilla Rakhimova"), (93, "Oksana Selekhmeteva"),
    (94, "Mananchaya Sawangkaew"), (95, "Anna Blinkova"), (96, "Taylor Townsend"),
    (97, "Polina Kudermetova"), (98, "Eva Lys"), (99, "Moyuka Uchijima"),
    (100, "Taylah Preston"),
]


def _norm_words(name: str) -> frozenset:
    if not name:
        return frozenset()
    txt = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return frozenset(w for w in re.split(r"[\s\-]+", txt.lower()) if w)


def _apply_list(db, tour: str, entries: list[tuple[int, str]], dry_run: bool) -> dict:
    report = {"updated": 0, "created": 0, "ambiguous": []}
    candidates = db.query(models.Player).filter(models.Player.tour == tour).all()
    by_words: dict[frozenset, list] = {}
    for p in candidates:
        key = _norm_words(p.name)
        if key:
            by_words.setdefault(key, []).append(p)

    now = datetime.utcnow()
    for rank, name in entries:
        key = _norm_words(name)
        matches = by_words.get(key, [])
        # Repli : sous-ensemble/sur-ensemble (second prénom manquant d'un
        # côté), même logique que scripts/dedupe_players.py.
        if len(matches) != 1:
            loose = [p for k, ps in by_words.items() for p in ps if len(k & key) >= 2 and (k <= key or key <= k)]
            if loose:
                matches = loose

        if len(matches) == 1:
            p = matches[0]
            if not dry_run:
                p.current_rank = rank
                p.current_rank_synced_at = now
            report["updated"] += 1
        elif len(matches) == 0:
            report["created"] += 1
            if not dry_run:
                p = models.Player(name=name, tour=tour, current_rank=rank, current_rank_synced_at=now)
                db.add(p)
                db.flush()
                by_words.setdefault(key, []).append(p)
        else:
            report["ambiguous"].append((rank, name, [p.name for p in matches]))

    if not dry_run:
        db.commit()
    return report


def run(dry_run: bool = False) -> dict:
    db = SessionLocal()
    try:
        return {
            "atp": _apply_list(db, "atp", ATP_TOP100, dry_run),
            "wta": _apply_list(db, "wta", WTA_TOP100, dry_run),
        }
    finally:
        db.close()


def main():
    dry_run = "--dry-run" in sys.argv
    report = run(dry_run=dry_run)
    mode = "SIMULATION (--dry-run, rien n'a été modifié)" if dry_run else "APPLIQUÉ"
    for tour, r in report.items():
        print(f"[apply_manual_rankings] {mode} -- {tour.upper()} : {r['updated']} mis à jour, "
              f"{r['created']} créé(s), {len(r['ambiguous'])} ambigu(s).")
        for rank, name, cands in r["ambiguous"]:
            print(f"    AMBIGU #{rank} '{name}' -> candidats : {cands}")


if __name__ == "__main__":
    sys.exit(main())
