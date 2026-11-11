# ADR-0002 — Banc d'essai de type hybride

- **Statut :** Accepté
- **Date :** 2026-11-08
- **Décideurs :** Auteur(s)

## Contexte

Le projet requiert de choisir un type de banc : simulation, émulation ou hybride, avec justification. Il faut arbitrer entre réalisme, reproductibilité, coût et conformité légale.

## Décision

Banc **hybride** : SUT **réel** (Co-ATC, logiciel exécuté), source de surveillance adverse **simulée au niveau du message** (fichier `aircraft.json` au format dump1090/tar1090, équivalent à la sortie d'un récepteur SDR après décodage).

## Alternatives envisagées

- **Émulation complète (SDR → RF → récepteur)** — écarté : exige une cage de Faraday, juridiquement sensible, gain faible pour l'étude des contre-mesures applicatives.
- **Simulation pure** — écarté : ne teste pas de logiciel de supervision réel.

## Conséquences

- Positives : réalisme du SUT + injection contrôlée, répétable et isolée ; démo « temps réel » faisable.
- Négatives : la fidélité s'arrête au message décodé ; la couche RF/PHY n'est pas couverte (voir ADR-0004 et limites du rapport).
- Suivi : documenter l'écart de fidélité comme limite ; suggestion d'amélioration = trames DF17 rejouées.
