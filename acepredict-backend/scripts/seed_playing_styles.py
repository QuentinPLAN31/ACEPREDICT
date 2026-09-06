"""
Seed unique : notes de style de jeu écrites à la main pour les joueurs
suffisamment établis/médiatisés pour qu'on soit vraiment sûr de ne pas
inventer (cf. models.py::Player.playing_style). Volontairement PAS
exhaustif : on couvre le haut du classement ATP/WTA et quelques vétérans
bien connus plus bas, et on s'arrête net dès que la confiance retombe (joueurs
trop récents/jeunes ou trop peu médiatisés pour qu'on ait une vraie
certitude sur leur style) -- mieux vaut une fiche absente qu'une fiche
inventée.

Usage :
    python -m scripts.seed_playing_styles

Idempotent : cherche chaque joueur par nom (insensible à la casse) + tour,
et écrase playing_style à chaque exécution (donnée de référence qu'on
contrôle nous-mêmes, pas une donnée synchronisée depuis une API externe).
Un nom non trouvé en base est juste ignoré (log), jamais bloquant -- le
joueur sera couvert dès qu'il existera en base (import Sackmann ou
auto-discovery LiveTennisAPI).
"""
from datetime import datetime

from app import models
from app.database import SessionLocal

# (nom exact tel qu'en base, tour, note de style)
STYLES = [
    # ---- ATP ----
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
    ("Felix Auger-Aliassime", "atp",
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

    # ---- WTA ----
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
]


def run():
    db = SessionLocal()
    updated, missing = 0, []
    try:
        for name, tour, note in STYLES:
            player = (
                db.query(models.Player)
                .filter(models.Player.name.ilike(name), models.Player.tour == tour)
                .first()
            )
            if not player:
                missing.append(f"{name} ({tour})")
                continue
            player.playing_style = note
            player.playing_style_updated_at = datetime.utcnow()
            updated += 1
        db.commit()
    finally:
        db.close()

    print(f"Style de jeu renseigné pour {updated}/{len(STYLES)} joueur(s).")
    if missing:
        print("Introuvables en base (pas encore importés, ou nom différent) :")
        for m in missing:
            print(f"  - {m}")


if __name__ == "__main__":
    run()
