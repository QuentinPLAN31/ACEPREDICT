# Déployer AcePredict en ligne

Guide pas-à-pas pour passer du local (`localhost`) à un vrai site
accessible sur internet. Suit l'ordre — chaque étape dépend de la
précédente.

## 0. Prérequis (à faire toi, je ne peux pas le faire à ta place)

- [ ] Statut légal pour encaisser de l'argent (auto-entrepreneur minimum en
      France — SIRET, IBAN). Sans ça, Stripe refusera d'activer le mode live.
- [ ] Compte Stripe créé et activé en mode live (après vérification
      d'identité par Stripe, peut prendre 1-3 jours).
- [ ] Un nom de domaine acheté (Gandi, Namecheap, OVH... ~10€/an).
- [ ] Réglé le point de la licence des données (voir `legal/mentions-legales.md`
      — les données actuelles sont non-commerciales, à remplacer avant de
      vendre l'accès).
- [ ] Documents légaux dans `legal/` relus par un professionnel.

## 1. Backend — héberger l'API

Recommandé pour démarrer : **Railway** (gratuit pour commencer, Postgres
managé inclus, déploie direct depuis un Dockerfile).

1. Crée un compte sur railway.app, connecte ton dépôt Git (pousse d'abord
   `acepredict-backend/` sur GitHub si ce n'est pas déjà fait).
2. "New Project" → "Deploy from GitHub repo" → sélectionne le dossier
   `acepredict-backend`.
3. Ajoute un service **PostgreSQL** dans le même projet (bouton "+ New" →
   "Database" → "PostgreSQL"). Railway génère `DATABASE_URL` automatiquement
   et l'injecte dans ton service API si tu les relies (Variables → Reference).
4. Dans les Variables du service API, ajoute toutes les clés de
   `.env.production.example` (sauf `DATABASE_URL`, déjà fournie par Railway).
5. Railway détecte le `Dockerfile` et déploie automatiquement. Le `CMD` du
   Dockerfile applique les migrations puis lance l'API — pas d'étape manuelle.
6. Une fois déployé, Railway te donne une URL du type
   `https://acepredict-backend-production.up.railway.app`. Vérifie
   `https://.../health` → doit répondre `{"status":"ok"}`.
7. Charge les vraies données : ouvre le "Shell" du service dans Railway et
   lance `python -m scripts.refresh_real_data` (une seule fois).

Alternative équivalente : **Render** (render.com), même principe
(Web Service + PostgreSQL managé), interface un peu différente.

## 2. Frontend — héberger landing.html / visitennis_1.html

Ce sont des fichiers statiques, hébergeables gratuitement sur **Vercel**,
**Netlify**, ou **Cloudflare Pages** (glisser-déposer le dossier suffit sur
Netlify).

**Avant de déployer**, remplace dans les DEUX fichiers HTML :
```js
const API_BASE = 'http://localhost:8000';
```
par l'URL réelle de ton backend Railway/Render (étape 1.6) :
```js
const API_BASE = 'https://acepredict-backend-production.up.railway.app';
```

## 3. Relier ton nom de domaine

- Frontend : dans Netlify/Vercel, "Domain settings" → ajoute ton domaine,
  suis les instructions DNS (ils indiquent les enregistrements à créer
  chez ton registrar).
- Backend : optionnel, tu peux garder l'URL Railway telle quelle, ou
  brancher un sous-domaine (`api.tondomaine.com`) sur le service Railway.

## 4. Mettre à jour le backend une fois le domaine actif

Dans les Variables Railway/Render du service API, mets à jour :
```
CORS_ORIGINS=https://tondomaine.com
```
Et dans `billing.py` (déjà dans le code), les URLs `success_url`/`cancel_url`
de Stripe Checkout pointent vers `localhost:5500` — à remplacer par ton
vrai domaine avant d'activer Stripe live (je peux le faire dès que tu me
donnes le domaine final).

## 5. Stripe en mode live

- Bascule ton dashboard Stripe de "Test mode" à "Live mode".
- Récupère les vraies clés `sk_live_...` et les vrais `price_id` de tes
  produits Starter/Pro/Lifetime (créés dans Stripe Dashboard → Produits).
- Mets-les dans les Variables Railway/Render (jamais dans le code, jamais
  commit dans git).
- Configure le webhook Stripe (Dashboard → Développeurs → Webhooks) vers
  `https://ton-backend/billing/webhook`, récupère le `whsec_...` généré.

## Ce qui reste à ma charge, dès que tu as avancé sur le 0-2

- Ajuster les URLs de callback Stripe vers ton vrai domaine.
- Vérifier bout-en-bout après déploiement (health check, inscription,
  analyse, paiement en mode test Stripe avant de basculer en live).
- Durcir la sécurité si besoin (rate limiting, monitoring d'erreurs).
