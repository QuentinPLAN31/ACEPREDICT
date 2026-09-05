# AcePredict — Backend

API FastAPI + PostgreSQL pour l'app de prédiction tennis AcePredict. Voir
[`ARCHITECTURE.md`](./ARCHITECTURE.md) pour le détail complet (endpoints,
schéma DB, moteur Elo, facturation).

**Pour que le site (`landing.html` / `visitennis_1.html`) soit utilisable —
connexion, recherche de joueurs, analyses, historique, compte, pricing —
ce backend doit tourner en local sur `http://localhost:8000`.** Voir "Lancer
le site complet" ci-dessous pour les deux commandes à exécuter.

## Lancer le site complet (frontend + backend)

Deux terminaux, deux commandes.

**Terminal 1 — le backend :**

```bash
cd acepredict-backend
cp .env.example .env
docker compose up --build
```

Ça y est : au premier démarrage, `docker compose` construit l'image, lance
Postgres, applique les migrations et **charge automatiquement des données de
démo réelles** (16 joueurs ATP, 6 tournois 2024, ratings Elo calculés) —
aucune commande manuelle supplémentaire. L'API tourne sur
`http://localhost:8000` (docs interactives sur `/docs`).

**Terminal 2 — le frontend**, depuis le dossier qui contient `landing.html` :

```bash
python3 -m http.server 5500
```

Puis ouvre `http://localhost:5500/landing.html` dans le navigateur.

> Pourquoi pas juste double-cliquer sur `landing.html` ? Ça fonctionne aussi
> (le backend autorise cette origine), mais servir les fichiers via un petit
> serveur local évite les restrictions que certains navigateurs appliquent
> aux pages ouvertes en `file://` — plus fiable pour une démo.

## Démarrage sans Docker

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # pointer DATABASE_URL vers votre Postgres local
python -m scripts.seed_demo   # migrations + données de démo, idempotent
uvicorn app.main:app --reload
```

## Utiliser les vraies données Jeff Sackmann

Le script d'ingestion attend le format CSV exact de
[JeffSackmann/tennis_atp](https://github.com/JeffSackmann/tennis_atp) (et
`tennis_wta` pour le circuit féminin). Chez vous (sans restriction réseau) :

```bash
git clone https://github.com/JeffSackmann/tennis_atp.git
python -m scripts.ingest_sackmann tennis_atp/atp_matches_2024.csv --tour atp
# répéter pour chaque année voulue, puis :
python -m scripts.compute_elo_ratings
```

## Tests

```bash
pytest tests/ -v
```

`tests/test_elo.py` et `tests/test_security.py` testent le moteur Elo et le
hashing de mot de passe (aucune base requise). `tests/test_health.py`
vérifie que l'app démarre (SQLite en mémoire pour l'import).

## Variables d'environnement clés

Voir `.env.example` pour la liste complète. Les indispensables pour démarrer :
`DATABASE_URL`, `JWT_SECRET`. Pour la facturation réelle : `STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STARTER/PRO/LIFETIME` — sans ces clés,
le bouton "Débloquer" de la page Pricing répond clairement que Stripe n'est
pas configuré plutôt que d'échouer silencieusement (mode démo). Pour le live :
`LIVETENNISAPI_KEY` (optionnelle selon le plan gratuit de l'API). Pour la
météo : `WEATHER_API_KEY` + `WEATHER_PROVIDER` (voir "Sources de données &
APIs" ci-dessous pour le choix entre les deux fournisseurs et leurs licences
respectives).

## Sources de données & APIs

Six sources externes ont été évaluées pour calculer la probabilité de
victoire (classement + forme + H2H + surface, ajustée par le marché et par
les conditions de jeu). Chacune a un rôle précis, un statut d'intégration,
et — point important pour un site monétisé (Stripe) — sa propre licence sur
l'usage commercial.

| # | Source | Rôle | Statut | Usage commercial |
|---|---|---|---|---|
| 1 | [Jeff Sackmann — tennis_atp/tennis_wta](https://github.com/JeffSackmann/tennis_atp) | Historique de matchs (1968+), entraîne l'Elo interne | ✅ Intégrée — import CSV (`scripts/ingest_sackmann.py`) | ⚠️ **CC BY-NC-SA — non-commercial only** |
| 2 | [Ultimate Tennis Statistics](https://github.com/mcekovic/tennis-crystal-ball) | Référence externe pour Elo/H2H | ❌ Non intégrée (décision volontaire, voir ci-dessous) | ⚠️ CC BY-NC-SA sur les ratings |
| 3 | [LiveTennisAPI.com](https://livetennisapi.com/subscribe/free) | Scores live, calendrier, fixtures, joueurs | ✅ Intégrée — `app/services/livetennis_client.py` | Pas de restriction connue |
| 4 | [The Odds API](https://the-odds-api.com/) | Cotes de bookmakers | ❌ Non intégrée — remplacée par Polymarket (voir ci-dessous) | — |
| 5 | [Open-Meteo](https://open-meteo.com/) | Météo (fournisseur alternatif) | ✅ Intégrée, **désactivée par défaut** — `app/services/weather_providers.py` | ⚠️ **Gratuit = non-commercial only** |
| 6 | [OpenWeatherMap](https://openweathermap.org/api) | Météo (fournisseur par défaut) | ✅ Intégrée, choisie par défaut | Pas de restriction connue |
| — | [Polymarket](https://polymarket.com) (Gamma API) | Probabilité de marché — remplace la source #4 | ✅ Intégrée — `app/services/polymarket_service.py` | Pas de restriction connue |

### 1. Jeff Sackmann — historique de matchs

Import CSV en local, pas d'appel API en temps réel (voir "Utiliser les
vraies données Jeff Sackmann" ci-dessus). ⚠️ **Cette donnée brute est sous
licence CC BY-NC-SA (non-commercial)** — à garder en tête avant un vrai
lancement commercial du site : soit obtenir un accord de licence auprès de
l'auteur, soit remplacer cette source par des données historiques sous
licence compatible.

### 2. Ultimate Tennis Statistics — pourquoi elle n'est PAS intégrée

Cette source n'a volontairement **pas** été branchée en direct : ses ratings
Elo/H2H sont sous licence CC BY-NC-SA, incompatible avec un site monétisé.
La bonne pratique documentée par la source elle-même s'applique déjà ici :
AcePredict **recalcule son propre Elo** à partir des données brutes Sackmann
(`app/services/elo.py`, rejoué à chaque match importé) plutôt que de
réutiliser des ratings tiers, et calcule son propre head-to-head à partir de
sa propre table `Match` (`prediction.py :: _head_to_head`) plutôt que de le
lire depuis UTS. Résultat : le même rôle (Elo par surface, H2H) est déjà
rempli en interne, sans dépendance à une source non-commercial-only.

### 3. LiveTennisAPI.com

Rôle : scores live, calendrier des prochains matchs, recherche de joueurs
(ATP/WTA/Challenger/ITF). Quota serré — **~30 req/min et ~100 req/jour** sur
le plan gratuit, le plus contraignant de toutes les sources ci-dessus.
`app/services/livetennis_client.py` met donc en cache en mémoire (TTL,
partagé par tout le process, pas par requête) chaque type d'appel :

| Donnée | TTL | Pourquoi |
|---|---|---|
| id d'un joueur (recherche par nom) | 1h | change (quasiment) jamais |
| ville d'un tournoi | 24h | ne change jamais en cours de tournoi |
| classement (rankings) | 1h | bouge au fil des résultats, pas à la minute |
| liste des prochains matchs | 2 min | équilibre fraîcheur / quota sous trafic concurrent |
| prochains matchs entre 2 joueurs | 2 min | idem |

### 4. The Odds API — pourquoi elle n'est PAS intégrée

Évaluée puis abandonnée : peu fiable en usage réel sur ce projet
(indisponibilités) pour un site qui doit rester utilisable. Remplacée par
**Polymarket** (`app/services/polymarket_service.py`), qui remplit le même
rôle — une probabilité implicite de marché pour calibrer/comparer le modèle
Elo interne (`prediction.py :: _apply_market_blend`) — sans clé, sans quota
mensuel à surveiller, avec un cache de 2 min sur la liste des marchés tennis
actifs. L'interface `MarketProvider` (`app/services/market_providers.py`)
garde la porte ouverte à un futur retour de The Odds API (ou une autre
source de cotes) si besoin, sans toucher à `prediction.py`.

### 5 et 6. Météo — Open-Meteo et OpenWeatherMap

Rôle : vent/température/humidité sur le lieu du tournoi, comme variable
d'ajustement de la probabilité (`prediction.py :: _weather_dampening`). Deux
fournisseurs interchangeables derrière une interface commune
`WeatherProvider` (`app/services/weather_providers.py`), choisis via
`WEATHER_PROVIDER` dans `.env` :

- **OpenWeatherMap** (`WEATHER_PROVIDER=openweathermap`, la valeur par
  défaut) : plan gratuit permanent (60 req/min, 1000 req/jour), clé requise,
  pas de restriction connue sur l'usage commercial — c'est le fournisseur à
  utiliser sur le site en production tant qu'il est monétisé.
- **Open-Meteo** (`WEATHER_PROVIDER=open-meteo`) : gratuite et sans clé,
  mais son offre gratuite est réservée par sa licence à un usage **NON
  COMMERCIAL** (https://open-meteo.com/en/pricing). Utile en dev/démo/projet
  scolaire sans même créer de compte — **à ne jamais activer en production
  sur ce site tant qu'il reste monétisé**, sans souscrire à leur offre
  commerciale.

Les deux mettent en cache géocodage (24h) et prévisions (30 min) séparément
pour limiter les appels sortants.

### Architecture "sources interchangeables"

Trois interfaces communes, chacune avec une seule fabrique à modifier pour
changer/ajouter un fournisseur, sans toucher aux appelants :

- `LiveDataClient` (`livetennis_client.py`) → `get_live_client()`
- `WeatherProvider` (`weather_providers.py`) → `get_weather_provider()`
- `MarketProvider` (`market_providers.py`) → `get_market_provider()`

## Synchronisation des données

**Le site n'appelle plus AUCUNE API externe en direct depuis une requête
utilisateur.** `GET /matches/upcoming`, `GET /matches/upcoming-list` et
`POST /analyses` lisent uniquement la base Postgres locale
(`routers/matches.py`, `routers/analyses.py`). Toutes les données externes
(historique de matchs, classements, prochains matchs, cotes de marché,
météo) sont synchronisées à l'avance par deux jobs planifiés, séparément de
toute requête HTTP entrante :

| Job | Fréquence | Script | Source(s) |
|---|---|---|---|
| Sync quotidienne | 1×/jour | `scripts/sync_daily.py` | CSV Jeff Sackmann (tour + qualifying/challenger + futures ATP, tour + qualifying/ITF WTA) |
| Sync horaire | 1×/heure | `scripts/sync_hourly.py` | LiveTennisAPI (fixtures + classements), Polymarket (cotes), OpenWeatherMap/Open-Meteo (météo) |

### Modèle de données

- **`Player.data_confidence`** (`insufficient` / `low` / `medium` / `high`,
  cf. `app/services/data_confidence.py`) : niveau de fiabilité des données
  disponibles pour ce joueur, recalculé par les deux jobs. `insufficient` =
  aucun historique connu et aucune fiche trouvée ; `low` = identifié via une
  source secondaire mais sans historique ; `medium` = historique réduit
  (< 15 matchs) ; `high` = historique substantiel. Ce niveau **n'empêche
  jamais l'analyse** : il est exposé au frontend (`player1_data_confidence`
  / `player2_data_confidence` sur `GET /matches/upcoming-list`) pour
  afficher un avertissement plutôt que de bloquer le bouton "Analyser".
- **`Player.current_rank`** : classement ATP/WTA officiel (distinct de
  l'Elo interne), mis à jour par la sync horaire.
- **Table `Fixture`** : un match À VENIR synchronisé depuis LiveTennisAPI,
  avec cotes de marché et météo dénormalisées directement sur la ligne
  (`market_player1_prob`, `weather_temp_c`, etc.) — remplace les tables
  séparées vu le volume (au plus un lookup marché + un lookup météo par
  fixture). `*_synced_at` distingue "jamais vérifié" de "vérifié, rien
  trouvé".

### Sync quotidienne (`scripts/sync_daily.py`)

Télécharge les derniers CSV Sackmann (5 fichiers : `atp_matches_{année}`,
`atp_matches_qual_chall_{année}`, `atp_matches_futures_{année}`,
`wta_matches_{année}`, `wta_matches_qual_itf_{année}`), les ingère
(`scripts/ingest_sackmann.py`, **idempotent** — un match déjà connu n'est
jamais dupliqué, identifié par compétition + joueurs + date + round),
recalcule l'Elo (`scripts/compute_elo_ratings.py`) puis `data_confidence`
pour tous les joueurs. Dégradation gracieuse fichier par fichier : un
fichier pas encore publié pour l'année en cours (ex: futures avant que
Sackmann ne l'ait créé) n'interrompt jamais les autres.

### Sync horaire (`scripts/sync_hourly.py`)

Pour l'ATP et la WTA : récupère le classement et la liste des prochains
matchs (LiveTennisAPI), puis pour chaque match, résout la ville du tournoi
et récupère cotes de marché + météo, le tout dénormalisé sur la Fixture.
Purge les fixtures qui ont disparu du calendrier live (match annulé/reporté)
ou dont la date est trop ancienne (déjà jouées).

**Auto-discovery** : dès qu'un joueur inconnu de notre base apparaît dans un
fixture, sa fiche est créée à la volée, puis enrichie via une tentative sur
LiveTennisAPI (recherche par nom) — c'est la seule "source secondaire"
réellement exploitable ici : TennisExplorer et l'ITF n'exposent aucune API
publique/gratuite utilisable sans scraping fragile, alors que LiveTennisAPI
couvre lui-même le Challenger/ITF (cf. sa documentation). Sans rien trouvé,
`data_confidence` passe à `insufficient` plutôt que de bloquer quoi que ce
soit — la fiche existe quand même, l'analyse tourne avec un Elo par défaut
(1500), juste avec l'avertissement de fiabilité approprié.

### Configuration GitHub Actions (recommandé en production)

`.github/workflows/sync-daily.yml` et `sync-hourly.yml` déclenchent les deux
scripts ci-dessus sur les crons `15 4 * * *` (quotidien) et `5 * * * *`
(horaire), plus `workflow_dispatch` pour un déclenchement manuel depuis
l'onglet Actions du repo. **Prérequis : un Postgres réellement déployé et
accessible depuis Internet** — le runner GitHub Actions n'a pas accès à un
`localhost` de votre machine.

À configurer dans *Settings → Secrets and variables → Actions* du repo :

| Secret | Obligatoire | Rôle |
|---|---|---|
| `DATABASE_URL` | ✅ | URL de connexion au Postgres de production |
| `LIVETENNISAPI_KEY` | Optionnel | Sans elle, la sync horaire se termine proprement sans rien synchroniser |
| `WEATHER_API_KEY` | Optionnel | Sans elle, les fixtures sont synchronisées sans météo |

Variables optionnelles (mêmes valeurs par défaut que `.env.example` si non
définies) : `LIVETENNISAPI_BASE_URL`, `WEATHER_PROVIDER`,
`POLYMARKET_ENABLED`, `POLYMARKET_BASE_URL`.

### "Ou équivalent" — alternative sans GitHub Actions

En développement, ou si le projet n'est pas (encore) poussé sur un repo
GitHub avec une base déployée, les deux jobs s'exécutent en une commande,
comme n'importe quel autre script de ce dossier :

```bash
python -m scripts.sync_daily
python -m scripts.sync_hourly
```

Pour une exécution périodique locale sans GitHub Actions, un cron (Linux)
ou un `launchd` (macOS) appelant ces deux commandes avec `DATABASE_URL`
pointé vers votre Postgres fait exactement le même travail — le contenu des
deux scripts est strictement identique quel que soit ce qui les déclenche.

## Ce qui est branché côté frontend

- **Connexion / inscription** (`landing.html`) → `POST /auth/register`, `POST /auth/login`.
- **Recherche de joueurs** (page Matchs) → `GET /players?q=...`.
- **Analyse d'un match** (bouton "Analyser le match avec l'IA") → `POST /analyses`, gating par quota inclus (402 si le quota du plan est atteint).
- **Historique** → `GET /analyses/history`.
- **Compte** (affichage + "Modifier" l'e-mail) → `GET /auth/me`, `GET /users/me/subscription`, `PATCH /users/me`.
- **Pricing** (boutons "Débloquer") → `POST /billing/checkout` (Stripe Checkout, ou message clair si Stripe n'est pas configuré).
- **Déconnexion** → suppression du token local, aucun appel réseau nécessaire.

Tout le reste (navigation, onglets de compétition, classement, tableau,
recherche de compétition) fonctionne côté frontend sans appel réseau —
c'est du contenu de démonstration, pas encore branché sur des données live
(voir `ARCHITECTURE.md` pour les pistes d'évolution : endpoints
`/competitions/*` déjà prêts côté API pour cette suite).
