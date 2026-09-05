# AcePredict — Architecture backend

> **Important** : les sections 1 à 7 ci-dessous sont des **hypothèses raisonnables déduites de l'usage visible du frontend** (landing.html + visitennis_1.html), pas du code réel d'un site existant — AcePredict est votre propre projet, il n'y a donc pas de "vrai backend" à reverse-engineer, seulement l'architecture qui a le plus de sens pour les fonctionnalités déjà construites côté frontend. La section 8 (`app/`, `scripts/`, `alembic/`, `tests/`) est en revanche du **code réellement fonctionnel**, testé dans cet environnement (voir "Preuves d'exécution" en bas de fichier), et branché sur les sources listées plus bas.

## 1. Fonctionnalités observées → opérations backend

| Fonctionnalité visible dans l'app | Opération backend déclenchée |
|---|---|
| Connexion / inscription (nav "Connexion", page Compte) | Auth (hash + vérif mot de passe, émission JWT) |
| Sidebar "Matchs" | Lecture des matchs à venir / live (DB + cache live) |
| Sidebar "Compétitions" → liste (Australian Open, Roland-Garros, Wimbledon, US Open, ATP/WTA Tour, Masters 1000, ATP Finals) | `GET /competitions` |
| Clic sur une compétition → page détail | `GET /competitions/{id}` + chargement des 5 onglets |
| Onglet "Classement" (+ sous-onglet "Tableau du tournoi") | `GET /competitions/{id}/ranking`, tableau calculé depuis les Elo courants |
| Onglet "Matchs" (résultats récents de la compét) | `GET /competitions/{id}/matches` |
| Onglet "Joueurs" (leaderboard) | `GET /players?tour=...&surface=...` trié par Elo |
| Onglet "Nations" | Agrégation SQL par pays sur `players` |
| Onglet "Analyse" (verrouillé, bouton "Passer Premium") | `POST /analyses` (protégé par plan + quota) |
| Page "Historique" | `GET /analyses/history` |
| Badge quota sidebar ("X analyses restantes") | `GET /users/me/subscription` |
| Page "Pricing" (Starter 10€, Pro 19€, Lifetime 99€) | `POST /billing/checkout` → Stripe Checkout |
| Sélecteur de langue (FR/EN/ES) | Traité côté frontend (i18n statique), aucun appel backend nécessaire |

## 2. API — endpoints probables

Voir aussi le schéma OpenAPI généré automatiquement (`/docs` une fois l'API lancée). Résumé :

```
POST   /auth/register            { email, password, full_name? } -> UserOut (201)
POST   /auth/login               form-urlencoded { username, password } -> { access_token, token_type }
GET    /auth/me                  (Bearer) -> UserOut

GET    /players?tour=&surface=&q=&limit=   -> [PlayerOut]
GET    /players/{id}                        -> PlayerOut

GET    /competitions                        -> [CompetitionOut]
GET    /competitions/{id}                   -> CompetitionOut
GET    /competitions/{id}/matches           -> [{ round, player1_id, player2_id, winner_id, score, date }]
GET    /competitions/{id}/ranking?tour=atp  -> [PlayerOut]  (top 32, trié Elo)

POST   /analyses   (Bearer, quota requis)
       { player1_id, player2_id, competition_id?, surface? }
       -> { predicted_winner_id, win_probability, model_version, detail }
GET    /analyses/history  (Bearer)          -> [AnalysisOut]

GET    /users/me/subscription (Bearer)      -> { plan, stripe_status, analyses_used, analyses_limit }

POST   /billing/checkout (Bearer)           { plan } -> { checkout_url }
POST   /billing/webhook                     (Stripe -> serveur, signature vérifiée)

GET    /health                              -> { status, env }
```

## 3. Base de données — modèle relationnel

Tables principales (voir `app/models.py` pour le détail complet des colonnes) :

- **users** — compte, `plan` (free/starter/pro/lifetime), `stripe_customer_id`.
- **subscriptions** — historique des abonnements Stripe (1 user → N lignes dans le temps).
- **usage_quotas** — compteur d'analyses consommées / limite du plan (1-1 avec `users`).
- **players** — joueurs ATP/WTA, `sackmann_id` pour relier aux CSV Jeff Sackmann, **Elo dénormalisé** (`elo_overall`, `elo_hard`, `elo_clay`, `elo_grass`) pour un affichage instantané du classement sans recalcul à la volée.
- **elo_history** — trace chaque mise à jour de rating (utile pour tracer une courbe de progression, non exposé en V1).
- **competitions** — Grand Chelem / Masters 1000 / ATP-WTA Tour / Finals, avec `season`.
- **matches** — matchs historiques (source `sackmann`) ou à venir (source `livetennisapi`), colonne `stats` en JSON(B) pour rester souple sur les stats détaillées (aces, doubles fautes...) sans multiplier les colonnes.
- **analyses** — une ligne par prédiction demandée par un user (alimente "Historique"), `detail` en JSON(B) pour les facteurs explicatifs.

**Mis en cache / dénormalisé** : `players.elo_*` (recalculé offline par `scripts/compute_elo_ratings.py`, pas à chaque requête).
**Recalculé à la volée** : la probabilité de victoire d'un match précis (`services/prediction.py`, quasi instantané — juste une formule logistique sur deux floats déjà en base).

## 4. Authentification & comptes

- **JWT stateless** (`app/security.py`, HS256) — pas de session serveur, cohérent avec un frontend statique/SPA. Token porté en `Authorization: Bearer <token>`.
- Mot de passe hashé avec **bcrypt** (`passlib`).
- Le **plan** (free/starter/pro/lifetime) est stocké sur `users.plan` et mis à jour par le webhook Stripe (`billing.py`) à la confirmation du paiement.
- Le **gating par plan** passe par `usage_quotas` : chaque plan a une limite d'analyses/mois (`PLAN_QUOTAS` dans `app/deps.py`), décrémentée à chaque `POST /analyses`. Dépassement → `402 Payment Required`.

## 5. Service de prédiction

Architecture retenue : **Elo par surface**, pas de ML lourd — c'est l'approche standard des projets de prédiction tennis publiés (voir Ultimate Tennis Statistics / tennis-crystal-ball, cité en source) et elle a l'avantage d'être explicable, rapide, et calculable avec un historique de matchs seul (pas besoin de features exotiques).

```
P(A bat B) = 1 / (1 + 10^((Elo_B - Elo_A) / 400))
```

Après chaque match : `Elo_gagnant += K·(1 - P(gagnant gagne))`, `Elo_perdant += K·(0 - P(perdant gagne))`, avec K=32.

- `app/services/elo.py` — moteur pur (aucune dépendance DB, testé unitairement dans `tests/test_elo.py`).
- `scripts/compute_elo_ratings.py` — job batch offline qui rejoue tout l'historique de `matches` et écrit les ratings sur `players.elo_*`.
- `app/services/prediction.py` — couche fine qui lit les Elo déjà stockés et calcule la probabilité pour une paire de joueurs donnée (endpoint `POST /analyses`).

**Pistes d'évolution** (non implémentées en V1, pour rester dans un scope raisonnable) : pondérer K par le nombre de matchs déjà joués par le joueur (K plus élevé pour un joueur "neuf" comme au chess Elo FIDE), ajouter un facteur de forme récente (rolling win-rate sur les 10 derniers matchs) et un historique tête-à-tête (H2H) comme features additionnelles d'un modèle de gradient boosting (XGBoost/LightGBM) entraîné sur `matches`, en gardant l'Elo comme feature principale.

## 6. Facturation / abonnements

- **Stripe Checkout** (`app/services/stripe_service.py`) : `POST /billing/checkout` crée une session Checkout Stripe (mode `subscription` pour Starter/Pro, mode `payment` pour Lifetime qui est un paiement unique) et retourne l'URL à rediriger.
- **Webhook** (`POST /billing/webhook`, signature vérifiée) : sur `checkout.session.completed`, met à jour `users.plan`, `users.stripe_customer_id`, la limite de `usage_quotas`, et insère une ligne `subscriptions`. Sur `customer.subscription.deleted`, repasse l'utilisateur en plan `free`.
- Mapping plans ↔ prix Stripe configuré via variables d'env (`STRIPE_PRICE_STARTER/PRO/LIFETIME`).

## 7. Schéma d'architecture global

```
┌─────────────┐      HTTPS/JSON       ┌──────────────────────┐
│  Frontend    │ ───────────────────▶ │   FastAPI (app/main)  │
│ landing.html │ ◀─────────────────── │  routers: auth,       │
│ visitennis_1 │      JWT Bearer      │  players, competitions,│
└─────────────┘                       │  analyses, users,      │
                                       │  billing               │
                                       └──────┬───────┬────────┘
                                              │       │
                          ┌───────────────────┘       └─────────────────┐
                          ▼                                             ▼
              ┌─────────────────────┐                        ┌──────────────────┐
              │ services/prediction  │                        │ services/stripe   │
              │ services/elo         │                        │ (Checkout/Webhook)│
              └──────────┬───────────┘                        └─────────┬────────┘
                         │                                              │
                         ▼                                              ▼
              ┌─────────────────────────────┐                 ┌──────────────────┐
              │  PostgreSQL (SQLAlchemy)     │                 │   Stripe API      │
              │  users, players, matches,    │                 └──────────────────┘
              │  competitions, analyses...   │
              └───────────┬──────────────────┘
                          │  alimenté offline par
                          ▼
       ┌───────────────────────────────────────────┐        ┌──────────────────────────┐
       │ scripts/ingest_sackmann.py                  │◀──────│ Jeff Sackmann tennis_atp/ │
       │ scripts/compute_elo_ratings.py               │        │ tennis_wta (CSV, GitHub)  │
       └───────────────────────────────────────────┘        └──────────────────────────┘

       ┌───────────────────────────────────────────┐
       │ services/livetennis_client.py                │──────▶ livetennisapi.com (live/calendrier/classements)
       └───────────────────────────────────────────┘
```

## 8. Livrable code — ce qui est réellement dans ce dépôt

Stack retenue (celle par défaut de votre propre prompt-template) : **Python + FastAPI + PostgreSQL** (SQLAlchemy + Alembic). Alternatives suggérées par votre "astuce pratique" (Supabase/Firebase/Django) : non retenues ici faute de choix explicite de votre part — dites-le si vous préférez basculer, la couche `app/services` et le moteur Elo sont indépendants du framework web et se portent facilement.

```
acepredict-backend/
├── app/
│   ├── main.py            # FastAPI app, montage des routers, CORS, /health
│   ├── config.py          # Settings (.env)
│   ├── database.py        # engine SQLAlchemy + get_db()
│   ├── models.py          # schéma relationnel (section 3)
│   ├── schemas.py         # Pydantic (validation API)
│   ├── security.py        # bcrypt + JWT
│   ├── deps.py             # get_current_user, gating quota/plan
│   ├── routers/            # auth, players, competitions, analyses, users, billing
│   └── services/
│       ├── elo.py                 # moteur Elo pur (testé)
│       ├── prediction.py          # orchestration prédiction
│       ├── livetennis_client.py   # client livetennisapi.com
│       └── stripe_service.py      # Checkout + webhooks
├── scripts/
│   ├── ingest_sackmann.py     # CSV Sackmann -> DB (players/competitions/matches)
│   └── compute_elo_ratings.py # rejoue l'historique -> met à jour les Elo
├── data/sample/atp_matches_sample.csv   # échantillon réaliste, même schéma que Sackmann
├── alembic/                    # migration initiale (schéma complet)
├── tests/                      # pytest : moteur Elo + démarrage API
├── requirements.txt, Dockerfile, docker-compose.yml, .env.example
```

### Sources de données branchées

- **Jeff Sackmann (tennis_atp / tennis_wta)** — `scripts/ingest_sackmann.py` lit directement le format CSV de ce dépôt (colonnes `winner_id`, `loser_name`, `tourney_date`, `surface`, `score`...). **Limitation technique de cet environnement de build** : l'accès au dépôt GitHub `JeffSackmann/tennis_atp` est bloqué pour cette session sandboxée (accès repo-par-repo non activé ici, confirmé via l'API GitHub et `raw.githubusercontent.com`) — ce n'est pas une limitation de votre côté. Le script est donc validé ici sur `data/sample/atp_matches_sample.csv`, un échantillon construit au **même schéma exact**, avec de vrais noms de joueurs (Alcaraz, Sinner, Djokovic...) sur 6 tournois 2024. Chez vous, sans cette restriction :
  ```bash
  git clone https://github.com/JeffSackmann/tennis_atp.git
  python -m scripts.ingest_sackmann tennis_atp/atp_matches_2024.csv --tour atp
  python -m scripts.compute_elo_ratings
  ```
- **livetennisapi.com** — `app/services/livetennis_client.py`, scores live / calendrier / classements. Clé optionnelle via `LIVETENNISAPI_KEY`.
- **Polymarket (Gamma API)** — `app/services/polymarket_service.py`, probabilité de marché fusionnée à la prédiction Elo (`services/prediction.py`). API publique, sans clé. Remplace The Odds API (abandonnée : payante et peu fiable en pratique).
- **SofaScore non-officiel** : volontairement absent du code (cf. votre consigne — prototypage seulement, jamais en prod). Si besoin ponctuel, implémenter la même interface `LiveDataClient` que `LiveTennisApiClient`.

### Preuves d'exécution (dans cet environnement, sans Postgres réel installé)

- `pytest tests/` → **5/5 tests passent** (moteur Elo + démarrage complet de l'app FastAPI, génération OpenAPI incluse).
- Pipeline complet exécuté sur SQLite en mémoire : création du schéma → ingestion des 42 matchs de l'échantillon → calcul Elo → `players` mis à jour (16 joueurs) → `POST /analyses` équivalent (`build_prediction`) retourne une probabilité cohérente.
- La migration Alembic initiale (`alembic/versions/fb24691d55af_initial_schema.py`) est écrite à la main (pas d'autogenerate, faute de serveur Postgres ici) mais reflète exactement `app/models.py` — à valider avec `alembic upgrade head` sur votre vraie base avant mise en prod.
