# Modèle de menaces — SecureID

## Périmètre

SecureID couvre l'émission, l'impression et la vérification hors ligne de cartes d'identité d'établissement.
Il ne remplace pas un titre officiel d'État et ne vise pas à en imiter un.

## Actifs à protéger

| Actif | Pourquoi |
|---|---|
| Clé privée de signature | Qui la détient peut fabriquer des cartes valides |
| Base SQLite (titulaires, cartes, comptes) | Données personnelles, historique des émissions |
| Journal d'audit | Preuve de qui a fait quoi |
| Liste de révocation | Empêche l'usage d'une carte perdue ou volée |
| Photos des titulaires | Données personnelles sensibles |

## Acteurs malveillants considérés

- **Fraudeur externe** : falsifie une carte ou en fabrique une fausse.
- **Porteur illégitime** : utilise une carte perdue, volée, expirée ou d'une autre personne.
- **Opérateur malveillant** : émet des cartes indues ou tente d'effacer ses traces.
- **Attaquant local** : a accès au poste d'émission (vol, session laissée ouverte).

## Menaces et parades (STRIDE)

| Catégorie | Menace | Parade dans SecureID |
|---|---|---|
| Usurpation | Fabriquer une fausse carte | Signature Ed25519 : impossible sans la clé privée |
| Usurpation | Se connecter avec le compte d'un autre | Argon2id, 12 caractères minimum, verrouillage après 5 échecs |
| Usurpation | Découvrir les identifiants existants | Message d'erreur identique, temps de calcul constant |
| Altération | Modifier nom, date ou statut sur la carte | Les données imprimées ne correspondent plus au QR signé |
| Altération | Remplacer la photo | Empreinte SHA-256 de la photo incluse dans les données signées |
| Altération | Retirer une carte de la liste de révocation | Liste signée : une liste modifiée est refusée |
| Altération | Modifier ou supprimer une ligne du journal | Chaînage SHA-256 : la rupture est détectée |
| Répudiation | Nier avoir émis ou révoqué une carte | Chaque action est journalisée au nom de l'opérateur connecté |
| Divulgation | Lire la clé privée sur le disque | Clé chiffrée (PKCS#8, mot de passe), dossier exclu de Git |
| Divulgation | Trop de données personnelles dans le QR | Minimisation : pas d'adresse ni de téléphone ; date de naissance absente du badge entreprise |
| Divulgation | Lire des fichiers via un import CSV piégé | Noms de photos sans chemin, refus de `..\` et `/` |
| Déni de service | Fichier d'import géant | Limite de 2 000 lignes par fichier |
| Élévation de privilèges | Un opérateur révoque des cartes ou crée des comptes | Rôles : ces actions sont réservées aux administrateurs |
| Élévation de privilèges | Session laissée ouverte | Déconnexion automatique après 10 minutes d'inactivité |

## Risques résiduels assumés

1. **Copie à l'identique** d'une carte valide (photocopie ou capture du QR) : la signature reste valide.
   Parade organisationnelle : comparer le visage avec la photo. Parade technique future : puce NFC à défi-réponse.
2. **Réécriture complète du journal** par quelqu'un qui a un accès en écriture à la base et recalcule toute la chaîne.
   Évolution prévue : signer régulièrement le dernier hash avec la clé de l'émetteur, ou l'ancrer hors du poste.
3. **Compromission du poste d'émission** pendant qu'il est déverrouillé : la clé est en mémoire.
   Évolution prévue : clé dans un HSM ou une carte à puce.
4. **Liste de révocation périmée** sur un poste de contrôle : la date de la liste est affichée en permanence
   pour inciter à la mettre à jour.
5. **Sécurités visuelles** (guilloches, micro-texte, pastille irisée) : elles compliquent la contrefaçon à l'œil,
   mais ne remplacent pas un vrai hologramme. La preuve d'authenticité reste la signature.
