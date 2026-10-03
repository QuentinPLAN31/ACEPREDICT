# Politique de confidentialité — BROUILLON À COMPLÉTER ET FAIRE VALIDER

> ⚠️ Modèle de structure pour un site avec compte utilisateur + paiement
> (RGPD, puisque tu vises probablement des utilisateurs en France/UE). Je ne
> suis pas avocat — fais valider avant publication. Les champs entre
> [crochets] sont à compléter.

## Qui sommes-nous

TennisMind (voir mentions-legales.md pour l'identité complète de l'éditeur).

## Données collectées

- **Compte utilisateur** : email, nom (optionnel), mot de passe (haché,
  jamais stocké en clair — c'est déjà le cas techniquement dans le backend).
- **Usage du service** : historique des analyses de matchs demandées,
  quota d'utilisation.
- **Paiement** : géré directement par Stripe — AcePredict ne stocke jamais
  de numéro de carte bancaire (uniquement un identifiant client Stripe).

## Finalité du traitement

- Fournir le service (authentification, analyses, historique).
- Facturation des abonnements payants.
- Emails transactionnels uniquement (ex. réinitialisation de mot de passe) — aucun email marketing à ce jour.

## Base légale (RGPD)

- Exécution du contrat (fourniture du service souscrit).
- Intérêt légitime (sécurité, prévention de la fraude).
- Consentement (si emails marketing — à ajouter uniquement si tu en
  envoies réellement, avec case à cocher explicite).

## Durée de conservation

Durée du compte actif, puis suppression/anonymisation sous [X mois] après clôture du compte, sauf obligation comptable de conservation plus longue.

## Droits des utilisateurs

Conformément au RGPD, chaque utilisateur peut demander l'accès,
la rectification, la suppression, ou la portabilité de ses données, en
écrivant à [email de contact].

## Sous-traitants / tiers

- **Stripe** (paiement) — politique de confidentialité Stripe applicable.
- **Railway Corporation** (hébergement backend/BDD) et **Vercel Inc.** (hébergement frontend).
- [LiveTennisAPI / The Odds API si branchés — préciser s'ils reçoivent des
  données utilisateur, normalement non].

## Cookies

Le site utilise uniquement le localStorage du navigateur pour le token de
connexion (usage technique, pas de bannière cookies requise). Aucun outil
de mesure d'audience ni traceur publicitaire (Google Analytics, Meta
Pixel, TikTok Pixel...) n'est utilisé à ce jour.

## Contact

Pour toute question sur tes données : tennismindsupport@gmail.com.
