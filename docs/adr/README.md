# Journal de décisions d'architecture (ADR)

Ce dossier consigne les **décisions structurantes** du projet (banc d'essai ADS-B / Co-ATC), au fur et à mesure.

Un ADR (*Architecture Decision Record*) capture **une** décision : son contexte, le choix retenu, les alternatives écartées et les conséquences. On n'édite pas un ADR accepté : s'il devient obsolète, on crée un nouvel ADR qui le **remplace** (`Supersedes`/`Superseded by`).

## Convention

- Un fichier par décision : `NNNN-titre-court.md` (numéro croissant).
- Statut : `Proposé` → `Accepté` → éventuellement `Remplacé` / `Abandonné`.
- Gabarit : [`0000-gabarit.md`](0000-gabarit.md).

## Index

| N° | Décision | Statut |
|----|----------|--------|
| [0001](0001-secteur-et-plateforme.md) | Secteur aéronautique et plateforme Co-ATC | Accepté |
| [0002](0002-type-de-banc-hybride.md) | Banc d'essai de type hybride | Accepté |
| [0003](0003-injection-faux-recepteur-http.md) | Injection par faux récepteur HTTP (tar1090) | Accepté |
| [0004](0004-contrainte-ethique-pas-de-rf.md) | Vase clos, aucune émission RF réelle | Accepté |
| [0005](0005-attaque-phare-clonage.md) | Attaque phare : clonage d'aéronefs | Accepté |
| [0006](0006-strategie-defense-plausibilite.md) | Défense : détecteur de plausibilité | Accepté |
| [0007](0007-proxy-intermediaire-python.md) | Proxy d'attaque Python (co-atc mono-source) | Accepté |
| [0008](0008-controle-conformite-et-approbations.md) | Contrôle de conformité et portes d'approbation | Accepté |
| [0009](0009-contrat-aircraft-json.md) | Contrat du flux `aircraft.json` servi par le proxy | Accepté |
| [0010](0010-sources-amont-proxy.md) | Sources amont du proxy (live / rejeu fichier / passthrough) | Accepté |
| [0011](0011-verite-terrain-et-evaluation.md) | Vérité terrain et évaluation (hors-bande) | Accepté |
| [0012](0012-parametres-experimentation.md) | Paramètres d'expérimentation des attaques | Accepté |
| [0013](0013-integration-detecteur.md) | Intégration du détecteur de défense | Accepté |
| [0014](0014-attaque-ciblee-v5.md) | Attaque ciblée V5 (avion fantôme / atterrissage forcé) | Accepté |
