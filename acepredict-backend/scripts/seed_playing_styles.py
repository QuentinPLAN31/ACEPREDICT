"""
Seed des notes de style de jeu (cf. models.py::Player.playing_style /
playing_style_confidence). Deux niveaux, jamais mélangés :

  1. HAUTE CONFIANCE : notes rédigées à la main pour les joueurs qu'on
     connaît vraiment bien (essentiellement le top ~30-40 de chaque tour,
     plus quelques vétérans très médiatisés situés plus bas au classement).
     Texte descriptif réel (coup dominant, main, tendance de jeu...).

  2. FAIBLE CONFIANCE : pour tout joueur en base avec un classement
     (Player.current_rank) <= STYLE_COVERAGE_RANK_LIMIT qui n'a PAS de note
     manuscrite ci-dessus -- on ne invente PAS un style qu'on ne connaît
     pas. On pose à la place une note honnête basée UNIQUEMENT sur une
     donnée sûre déjà en base (la main, si connue), explicitement marquée
     "faible" -- le frontend affiche alors un avertissement "information
     incertaine / couverture éditoriale limitée" plutôt que de faire
     passer ce texte pour une vraie analyse de style.

Usage :
    python -m scripts.seed_playing_styles

Idempotent, à relancer après chaque mise à jour des classements (le
fallback "faible" dépend de Player.current_rank, rempli par le job horaire
scripts/sync_hourly.py -- tant qu'aucun classement n'est encore synchronisé,
current_rank est NULL partout et seule la liste manuscrite ci-dessous est
appliquée).
"""
from datetime import datetime

from app import models
from app.database import SessionLocal

# Rang officiel (Player.current_rank) en-deçà duquel on pose au moins un
# fallback "faible" pour un joueur non couvert par la liste manuscrite.
STYLE_COVERAGE_RANK_LIMIT = 150

# (nom exact tel qu'en base, tour, note de style) -- toutes en confiance "haute".
STYLES_HAUTE = [
    # ================= ATP =================
    ("Jannik Sinner", "atp",
     "Jeu extrêmement plat et puissant des deux côtés, frappe la balle très tôt "
     "après le rebond, redoutable en échange de fond de court, peu d'amorties. "
     "Service solide sans être le plus explosif du circuit. Grande régularité mentale."),
    ("Carlos Alcaraz", "atp",
     "Jeu très complet et créatif, énormément de variation (amorties, montées au "
     "filet, accélérations soudaines). Capable de changer radicalement de rythme "
     "en plein échange. Excellent sur toutes surfaces."),
    ("Alexander Zverev", "atp",
     "Service et coup droit/revers à deux mains très puissants depuis le fond du "
     "court. Jeu de puissance pure, peu porté sur le filet. Peut être fragile "
     "mentalement dans les moments serrés."),
    ("Felix Auger Aliassime", "atp",
     "Gros service et coup droit puissant, jeu plus direct et agressif. Revers à "
     "deux mains parfois moins fiable sous pression que le reste de son jeu."),
    ("Novak Djokovic", "atp",
     "Retour de service parmi les meilleurs de l'histoire du jeu, extrême "
     "solidité en défense, revers à deux mains très fiable. Capable de prolonger "
     "les échanges pour épuiser l'adversaire plutôt que de forcer le gain du point."),
    ("Ben Shelton", "atp",
     "Gaucher, service parmi les plus puissants du circuit, jeu explosif et "
     "agressif, coup droit très lifté. Revers à une main, atypique pour un "
     "joueur formé aux Etats-Unis."),
    ("Daniil Medvedev", "atp",
     "Jeu atypique, se place très loin derrière la ligne de fond, redoutable en "
     "contre et en variation de rythme. Revers à deux mains très fiable. Sert "
     "bien sans être explosif ; excellent lecteur du jeu adverse."),
    ("Alex de Minaur", "atp",
     "Vitesse de déplacement exceptionnelle, jeu de contre-attaque et de "
     "récupération, physique quasi inépuisable. Moins de puissance brute que "
     "les autres joueurs du top, compense par la régularité et la course."),
    ("Taylor Fritz", "atp",
     "Gros service et coup droit puissant, jeu plus direct avec peu de variation. "
     "Revers à deux mains solide, cherche à imposer sa puissance de fond de court."),
    ("Arthur Fils", "atp",
     "Jeune joueur très offensif, gros coup droit, sert bien, style spectaculaire "
     "et agressif porté vers l'attaque."),
    ("Frances Tiafoe", "atp",
     "Jeu athlétique et créatif, énormément de talent naturel, revers à deux "
     "mains. Capable d'un tennis spectaculaire mais dans l'ensemble irrégulier "
     "d'un match à l'autre."),
    ("Lorenzo Musetti", "atp",
     "Revers à une main élégant, jeu très varié avec beaucoup de slice et "
     "d'amorties. Historiquement plus à l'aise sur terre battue que sur dur."),
    ("Alexander Bublik", "atp",
     "Jeu extrêmement atypique et imprévisible : service kické, amorties "
     "surprises, coups peu conventionnels. Grande puissance de service, mais "
     "mental parfois instable d'un jeu à l'autre."),
    ("Brandon Nakashima", "atp",
     "Jeu solide et régulier, peu de coups spectaculaires, bon retour de "
     "service. Style plus classique et discret que la plupart du top 20."),
    ("Casper Ruud", "atp",
     "Spécialiste historique de la terre battue, coup droit très lifté inspiré "
     "du style Nadal, revers à deux mains. Jeu patient construit depuis le fond "
     "du court."),
    ("Andrey Rublev", "atp",
     "Coup droit extrêmement puissant frappé très tôt, jeu très agressif et "
     "rythmé porté vers l'attaque. Tempérament explosif et démonstratif sur le court."),
    ("Cameron Norrie", "atp",
     "Gaucher, jeu de grinder très lifté et très physique. Mise davantage sur la "
     "régularité et l'endurance que sur la puissance pure."),
    ("Ugo Humbert", "atp",
     "Gaucher, jeu varié avec un slice de revers travaillé, bon service, style élégant."),
    ("Matteo Berrettini", "atp",
     "Gros service et coup droit puissants, jeu offensif porté vers le filet. "
     "Historiquement sujet aux blessures qui ont freiné sa progression."),
    ("Hubert Hurkacz", "atp",
     "Un des plus gros services du circuit, jeu de puissance avec peu de "
     "variation, monte occasionnellement au filet derrière son service."),
    ("Denis Shapovalov", "atp",
     "Gaucher, revers à une main spectaculaire, jeu à très haut risque avec des "
     "prises de balle très tôt. Très inconstant d'un match à l'autre."),
    ("Karen Khachanov", "atp",
     "Jeu de puissance classique depuis le fond du court, gros coup droit, "
     "profil plus solide que créatif."),
    ("Stefanos Tsitsipas", "atp",
     "Revers à une main, jeu offensif construit autour d'un coup droit "
     "inside-out puissant, historiquement à l'aise sur terre battue."),
    ("Grigor Dimitrov", "atp",
     "Jeu élégant et complet, revers à une main, excellent toucher de balle. "
     "Carrière freinée par des blessures récurrentes."),
    ("Holger Rune", "atp",
     "Jeu très agressif et physique, gros coup droit, prise de risque élevée, "
     "tempérament parfois instable sur le court."),
    ("Sebastian Baez", "atp",
     "Spécialiste de la terre battue, petit gabarit, jeu de grinder avec "
     "énormément de topspin depuis le fond du court."),
    ("Jack Draper", "atp",
     "Gaucher, gros coup gauche et jeu physique, longtemps freiné par les "
     "blessures avant de percer durablement."),
    ("Adrian Mannarino", "atp",
     "Gaucher, jeu très à plat et très varié, style atypique et difficile à "
     "lire, prend la balle tôt sans forcer."),
    ("Gael Monfils", "atp",
     "Athlète explosif, jeu spectaculaire et créatif, couverture de terrain "
     "exceptionnelle, mentalement irrégulier, en fin de carrière."),
    ("Stan Wawrinka", "atp",
     "Revers à une main parmi les plus puissants de l'histoire du jeu, coup "
     "gagnant redoutable en fin d'échange, en fin de carrière."),
    ("Nick Kyrgios", "atp",
     "Jeu extrêmement talentueux et créatif, gros service, énormément "
     "d'amorties. Très irrégulier, activité réduite ces dernières saisons "
     "(blessures)."),
    ("Borna Coric", "atp",
     "Jeu solide et régulier sans coup extrême, profil de grinder plus que d'attaquant."),
    ("Sebastian Korda", "atp",
     "Jeu élégant avec un bon toucher de balle, revers à une main, service efficace."),
    ("Alexei Popyrin", "atp",
     "Grand gabarit, gros service et coup droit puissant, jeu plus direct que varié."),
    ("Yoshihito Nishioka", "atp",
     "Petit gabarit, jeu de contre très rapide et régulier, spécialiste du retour de service."),

    # ================= WTA =================
    ("Aryna Sabalenka", "wta",
     "Service et coup droit parmi les plus puissants du circuit féminin, jeu "
     "très agressif joué proche de la ligne de fond, cherche à dicter l'échange "
     "dès les premières balles."),
    ("Elena Rybakina", "wta",
     "Service considéré comme l'un des meilleurs du circuit féminin, frappe très "
     "plate et très puissante. Peu d'émotion apparente sur le court, jeu de "
     "puissance pure."),
    ("Jessica Pegula", "wta",
     "Jeu solide et très régulier, moins de coups gagnants spectaculaires que le "
     "reste du top 10, mais excellente lecture tactique et revers à deux mains fiable."),
    ("Coco Gauff", "wta",
     "Vitesse de déplacement exceptionnelle, jeu défensif retravaillé vers plus "
     "d'agressivité ces dernières saisons. Le service a longtemps été son point "
     "faible principal, en progrès continu."),
    ("Mirra Andreeva", "wta",
     "Joueuse jeune mais déjà très complète, bon toucher de balle et variation, "
     "solidité depuis le fond de court et maturité tactique au-dessus de son âge."),
    ("Karolina Muchova", "wta",
     "Revers à une main, rare chez les femmes, jeu tout en toucher et en "
     "variation. Capable de coups très créatifs (amorties, slices, accélérations "
     "soudaines) plutôt que de puissance pure."),
    ("Iga Swiatek", "wta",
     "Coup droit extrêmement lifté et topspin, spécialiste historique de la "
     "terre battue. Déplacement excellent, jeu construit sur la puissance de "
     "rotation plus que sur la frappe plate."),
    ("Elina Svitolina", "wta",
     "Jeu défensif et très régulier, excellente couverture de terrain. Moins de "
     "puissance brute que les autres joueuses du top, compense par la constance."),
    ("Amanda Anisimova", "wta",
     "Coup droit et revers à deux mains très puissants, jeu offensif construit "
     "depuis le fond du court."),
    ("Belinda Bencic", "wta",
     "Jeu solide et complet, bonne régularité, revers à deux mains fiable, "
     "profil plus tacticien que puissance pure."),
    ("Naomi Osaka", "wta",
     "Coup droit et service très puissants quand elle est en confiance, jeu "
     "offensif de puissance. Peut être irrégulière mentalement d'un tournoi à l'autre."),
    ("Ekaterina Alexandrova", "wta",
     "Jeu puissant et plat, frappe la balle tôt, service solide, cherche à "
     "prendre l'initiative dès l'échange."),
    ("Elise Mertens", "wta",
     "Jeu polyvalent et régulier, également l'une des meilleures joueuses de "
     "double du circuit, ce qui se traduit par un bon sens du placement en simple."),
    ("Jasmine Paolini", "wta",
     "Petit gabarit, jeu très rapide et agressif, énorme énergie sur le court, "
     "revers à deux mains, compense le manque de puissance brute par la vitesse."),
    ("Madison Keys", "wta",
     "Un des coups droits les plus puissants du circuit féminin, service "
     "puissant, jeu de puissance pure recherchant le point gagnant rapidement."),
    ("Jelena Ostapenko", "wta",
     "Jeu extrêmement agressif et à très haut risque, frappe la balle très tôt "
     "et très fort sur presque toutes les surfaces de court. Peut gagner très "
     "vite ou s'effondrer tout aussi vite."),
    ("Maria Sakkari", "wta",
     "Physique exceptionnel, jeu de puissance et de course, très solide en "
     "échange de fond de court, grande capacité de récupération entre les points."),
    ("Barbora Krejcikova", "wta",
     "Jeu tout en toucher et en variation, moins de puissance brute que la "
     "moyenne du top 30, excellente tacticienne (également très forte en double)."),
    ("Donna Vekic", "wta",
     "Jeu solide et complet sans particularité extrême, profil plus régulier que spectaculaire."),
    ("Emma Navarro", "wta",
     "Jeu solide et régulier, bonne tacticienne, moins de puissance brute que "
     "la moyenne du top 30."),
    ("Daria Kasatkina", "wta",
     "Jeu tout en variation (slices, amorties, changements de rythme), moins de "
     "puissance que la moyenne, très bonne défenseuse."),
    ("Victoria Azarenka", "wta",
     "Jeu de puissance avec prise de balle très tôt, expérience de très haut "
     "niveau, carrière en fin de parcours."),
    ("Caroline Garcia", "wta",
     "Jeu offensif et agressif, gros coup droit et service puissant, résultats "
     "historiquement irréguliers d'un tournoi à l'autre."),
    ("Leylah Fernandez", "wta",
     "Gauchère, jeu créatif avec beaucoup de variation, grande combativité "
     "mentale dans les matchs serrés."),
    ("Petra Kvitova", "wta",
     "Gauchère, jeu extrêmement plat et puissant, frappe la balle très tôt, "
     "activité réduite en fin de carrière."),
    ("Marketa Vondrousova", "wta",
     "Gauchère, jeu tout en variation et en toucher, peu de puissance brute, "
     "beaucoup de slices et de changements de rythme."),
    ("Ons Jabeur", "wta",
     "Jeu extrêmement créatif avec énormément d'amorties et de slices, l'un des "
     "styles les plus atypiques du circuit féminin."),
    ("Beatriz Haddad Maia", "wta",
     "Gauchère, jeu physique et puissant, beaucoup de topspin, profil de terrienne."),
    ("Magda Linette", "wta",
     "Jeu régulier et discret, profil plus tacticien que puissance brute."),
    ("Sloane Stephens", "wta",
     "Jeu de contre-attaque et de défense, très bonne vitesse de déplacement."),
    ("Katie Boulter", "wta",
     "Gros service et coup droit, jeu plus direct que varié."),
]

# Fallback honnête pour un joueur classé (current_rank <= STYLE_COVERAGE_RANK_LIMIT)
# mais absent de STYLES_HAUTE ci-dessus : on ne connaît pas assez ce joueur pour
# décrire un vrai style, donc on ne décrit RIEN d'inventé -- seule la main
# (donnée sûre déjà en base) est mentionnée si connue.
def _fallback_note(player) -> str:
    if player.hand and player.hand.upper() in ("R", "L"):
        main = "gaucher" if player.hand.upper() == "L" else "droitier"
        return (
            f"Peu d'informations de style disponibles pour ce joueur à ce niveau de "
            f"classement (couverture éditoriale limitée) -- seule donnée fiable connue : {main}."
        )
    return (
        "Peu d'informations de style disponibles pour ce joueur à ce niveau de "
        "classement (couverture éditoriale limitée)."
    )


def run():
    db = SessionLocal()
    updated_haute, missing = 0, []
    try:
        for name, tour, note in STYLES_HAUTE:
            player = (
                db.query(models.Player)
                .filter(models.Player.name.ilike(name), models.Player.tour == tour)
                .first()
            )
            if not player:
                missing.append(f"{name} ({tour})")
                continue
            player.playing_style = note
            player.playing_style_confidence = "haute"
            player.playing_style_updated_at = datetime.utcnow()
            updated_haute += 1
        db.commit()

        # Fallback "faible" : tout joueur classé dans la limite, sans note haute.
        candidates = (
            db.query(models.Player)
            .filter(
                models.Player.current_rank.isnot(None),
                models.Player.current_rank <= STYLE_COVERAGE_RANK_LIMIT,
                models.Player.playing_style.is_(None),
            )
            .all()
        )
        for player in candidates:
            player.playing_style = _fallback_note(player)
            player.playing_style_confidence = "faible"
            player.playing_style_updated_at = datetime.utcnow()
        db.commit()
        updated_faible = len(candidates)
    finally:
        db.close()

    print(f"Style haute confiance renseigné pour {updated_haute}/{len(STYLES_HAUTE)} joueur(s).")
    print(f"Style faible confiance (fallback) posé pour {updated_faible} joueur(s) classé(s) <= {STYLE_COVERAGE_RANK_LIMIT}.")
    if missing:
        print("Introuvables en base parmi la liste haute confiance (pas encore importés, ou nom différent) :")
        for m in missing:
            print(f"  - {m}")
    if updated_faible == 0:
        print("Aucun fallback posé : Player.current_rank est probablement encore vide partout "
              "(classements pas encore synchronisés, cf. scripts/sync_hourly.py) -- relance ce "
              "script après le premier sync horaire réussi.")


if __name__ == "__main__":
    run()
