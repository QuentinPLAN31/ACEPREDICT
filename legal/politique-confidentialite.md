# Politique de confidentialité — BROUILLON À COMPLÉTER ET FAIRE VALIDER

> ⚠️ Modèle de structure pour un site avec compte utilisateur + paiement
> (RGPD, puisque tu vises probablement des utilisateurs en France/UE). Je ne
> suis pas avocat — fais valider avant publication. Les champs entre
> [crochets] sont à compléter.

## Qui sommes-nous

[Ton nom / ta société], éditeur du site AcePredict, accessible à
l'adresse [URL du site].

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
- [Ajouter si applicable : emails transactionnels, statistiques d'usage
  anonymisées, etc.]

## Base légale (RGPD)

- Exécution du contrat (fourniture du service souscrit).
- Intérêt légitime (sécurité, prévention de la fraude).
- Consentement (si emails marketing — à ajouter uniquement si tu en
  envoies réellement, avec case à cocher explicite).

## Durée de conservation

[À définir — ex: durée du compte actif + X mois après suppression].

## Droits des utilisateurs

Conformément au RGPD, chaque utilisateur peut demander l'accès,
la rectification, la suppression, ou la portabilité de ses données, en
écrivant à [email de contact].

## Sous-traitants / tiers

- **Stripe** (paiement) — politique de confidentialité Stripe applicable.
- **[Hébergeur choisi]** (hébergement des données).
- [LiveTennisAPI / The Odds API si branchés — préciser s'ils reçoivent des
  données utilisateur, normalement non].

## Cookies

[À compléter selon ce que tu utilises réellement — actuellement le site
n'utilise que le localStorage du navigateur pour le token de connexion, pas
de cookies tiers ni de tracking publicitaire, à confirmer/adapter si ça
change].

## Contact

Pour toute question sur tes données : [email de contact].
