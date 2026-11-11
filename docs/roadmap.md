# Feuille de route — incréments du banc d'essai ADS-B

Plan de travail du projet, découpé en **incréments courts et verticaux**. Règle d'or : chaque incrément se termine par un **état démontrable et vérifiable**, et ne commence qu'après que le précédent est « Terminé ». Les décisions structurantes sont consignées en ADR ; chaque livraison passe par l'agent conformité ([ADR-0008](adr/0008-controle-conformite-et-approbations.md)).

## Principe d'avancement

Pour chaque incrément :
1. **Pré-requis** : ADR à écrire/valider avant de coder.
2. **Agent pilote** : qui fait le travail.
3. **Livrable** : ce qui est produit.
4. **Critère de sortie** (*Definition of Done*) : condition observable qui prouve que c'est fini.
5. **Porte conformité** : passage de `adsb-conformite-securite` avant de clôturer.

On ne saute pas d'étape : un incrément non « Terminé » bloque le suivant.

## Vue d'ensemble

| # | Incrément | Agent pilote | ADR | Statut |
|---|-----------|--------------|-----|--------|
| INC-0 | Socle : co-atc en marche (référence) | — / orchestrateur | 0001 | Terminé (OpenSky OAuth2, trafic réel affiché) |
| INC-1 | Proxy transparent (pass-through) | adsb-dev-attaque | 0009 ✓ | En cours (code écrit, à vérifier) |
| INC-2 | UI de pilotage + squelette du moteur | adsb-dev-attaque | 0010 | Terminé (UI : source + attaques décrites) |
| INC-3 | Attaque V1 — clonage | adsb-dev-attaque | 0005, 0011 | Terminé (clonage + vérité terrain, testé hors-ligne) |
| INC-4 | Attaques V2 / V3 / V4 | adsb-dev-attaque | 0012 | Terminé (V2/V3/V4 + mode traj. V1) |
| INC-5 | Détecteur de défense D1/D2 | adsb-dev-defense | 0006 ✓, 0013 | Terminé (détecteur + métriques V1-V4) |
| INC-6 | Expérimentation + rapport + démo | adsb-redacteur | — | En cours (rapport LaTeX ébauché) |

Phase transverse continue : **adsb-chercheur** (modèle de menace) et **adsb-redacteur** (rapport) alimentés au fil des incréments.

---

## INC-0 — Socle : co-atc en marche (référence)

- **But** : disposer d'une base de comparaison « avant attaque ».
- **Pré-requis** : aucun.
- **Livrable** : co-atc compilé et lancé (`./bin/co-atc`), source en rejeu `data/*.db` ou OpenSky anonyme.
- **Critère de sortie** : la carte affiche du trafic ; on note l'état nominal (nombre de pistes, alertes). Capture d'écran de référence rangée dans `docs/`.
- **Porte conformité** : lecture seule, rien de sensible.

## INC-1 — Proxy transparent (pass-through)

- **But** : prouver l'**interposition** sans encore attaquer. C'est l'incrément le plus important : s'il marche, toute la suite n'est que des transformations.
- **Pré-requis** : **ADR-0009** — contrat du `aircraft.json` servi (champs minimaux attendus par co-atc : `hex`, `lat`, `lon`, `alt_baro`, `gs`, `track`, `squawk`, `seen`…), validé contre la struct `ADSBTarget`.
- **Agent** : adsb-dev-attaque.
- **Livrable** : app Python (FastAPI) dans `attack-proxy/` qui récupère la source amont et ré-expose `GET /aircraft.json` **sans modification** ; co-atc basculé sur `source_type=readsb-api`.
- **Critère de sortie** : co-atc affiche **le même trafic** via le proxy qu'en direct (comparaison avec la référence INC-0). Aucun champ perdu.
- **Porte conformité** : vérifier dossier séparé, co-atc core intact, pas de secret commité, changement de `config.toml` approuvé.

## INC-2 — UI de pilotage + squelette du moteur

- **But** : pouvoir activer/désactiver des attaques (encore sans effet) depuis une page web.
- **Agent** : adsb-dev-attaque.
- **Livrable** : UI web (toggles + paramètres) + état partagé en mémoire lu par le moteur ; attaques câblées en « no-op ».
- **Critère de sortie** : activer une attaque dans l'UI change l'état visible côté serveur ; le flux reste pass-through tant qu'aucune transformation n'est écrite.
- **Porte conformité** : pas d'appel réseau nouveau hors localhost.

## INC-3 — Attaque V1 : clonage (pièce maîtresse)

- **But** : la démo phare — rendre le vrai indiscernable des leurres.
- **Pré-requis** : [ADR-0005](adr/0005-attaque-phare-clonage.md).
- **Agent** : adsb-dev-attaque.
- **Livrable** : transformation de clonage paramétrable (facteur N, bruit position/cap/alt, hex distincts, même indicatif/type).
- **Critère de sortie** : en activant V1, co-atc affiche réel + N leurres portant la même étiquette à des positions différentes. **Démo reproductible** à partir du rejeu.
- **Porte conformité** : toujours en vase clos, aucune émission RF.

## INC-4 — Attaques V2 / V3 / V4

- **But** : couvrir ≥ 2 vulnérabilités (objectif du projet) avec marge.
- **Pré-requis** : **ADR-0010** — paramètres d'expérimentation (N, amplitude de bruit, cadence, nombre de cibles flooding).
- **Agent** : adsb-dev-attaque.
- **Livrable** : V2 dérive de trajectoire, V3 squawk 7500/7600/7700, V4 flooding.
- **Critère de sortie** : chaque attaque est activable indépendamment et son effet est observable sur co-atc (fausse route, fausse urgence, dégradation d'affichage).
- **Porte conformité** : revue de périmètre (ne pas déborder sur du code co-atc).

## INC-5 — Détecteur de défense D1/D2

- **But** : la remédiation démontrable (6 pts au rapport).
- **Pré-requis** : [ADR-0006](adr/0006-strategie-defense-plausibilite.md) ; passage à `Accepté` en fin d'incrément.
- **Agent** : adsb-dev-defense.
- **Livrable** : module séparé scorant les pistes (D1 cinématique + D2 métadonnées) ; vérité terrain fournie par le proxy pour l'évaluation.
- **Critère de sortie** : tableau **précision/rappel** par scénario V1–V4, avant/après défense ; faux positifs documentés.
- **Porte conformité** : module séparé, co-atc core intact.

## INC-6 — Expérimentation, rapport et démo

- **But** : produire les livrables notés (rapport 40 %, présentation 40 %).
- **Agent** : adsb-redacteur.
- **Livrable** : rapport LaTeX (plan retenu, environ 15 p., références IEEE réelles), schémas exportés depuis `docs/diagrams/`, scénario de démo + **vidéo de secours** (recommandée).
- **Critère de sortie** : rapport complet et cohérent avec les ADR ; démo rejouable en temps réel.
- **Porte conformité** : vérification finale (aucune référence inventée, aucune publication en ligne sans accord).

---

## Structure de dépôt cible (apport du projet, hors cœur co-atc)

```
attack-proxy/                 # tout notre code — séparé de co-atc
  app.py                      # FastAPI : endpoint /aircraft.json + UI + API de contrôle
  upstream/                   # fetcher amont (OpenSky / tar1090 / rejeu .db)
  attacks/                    # moteur : v1_clone.py, v2_trajectory.py, v3_squawk.py, v4_flood.py
  state.py                    # configuration d'attaque partagée (lue à chaque cycle)
  web/                        # page de pilotage (toggles + paramètres)
  config.example.toml
  README.md                   # lancement + config co-atc à appliquer
defense/                      # INC-5 : détecteur D1/D2 + évaluation (module séparé)
docs/                         # proposition, architecture, ADR, diagrammes, rapport
```

## Points en attente (à reprendre)

- **CYUL / config.example** : `configs/config.toml` est passé à Montréal (CYUL) mais reste gitignoré (local). À décider plus tard : reporter ou non les coordonnées CYUL dans `configs/config.toml.example` (versionné), et câbler des URLs de flux radio CYUL vérifiées.

## Suivi

Ce fichier est tenu à jour à chaque incrément (colonne Statut : À faire → En cours → Terminé). Toute décision structurante rencontrée en chemin donne lieu à un nouvel ADR avant de coder.
