# ADR-0011 — Vérité terrain et évaluation

- **Statut :** Accepté
- **Date :** 2026-11-09
- **Décideurs :** Auteur(s)
- **Lié à :** ADR-0005 (clonage), INC-3, INC-5 (défense)

## Contexte

Le but de l'attaque de clonage est que l'opérateur co-atc **ne puisse pas** distinguer les leurres. Mais nous (analystes) et le détecteur de défense (pour être évalué) avons besoin de connaître la **vérité terrain** : quelles cibles sont fausses, et de quel avion réel elles sont la copie.

## Décision

La vérité terrain est tenue **hors-bande**, jamais dans le flux servi à co-atc :

- Le moteur d'attaques produit, à chaque cycle, en plus des cibles, une structure de vérité : pour chaque leurre, son `hex`, l'`hex` de l'original (`clone_of`) et l'attaque responsable.
- Le proxy l'expose via `GET /api/truth` (lecture seule) et un **mode « révéler »** dans l'UI du proxy. **co-atc ne la voit jamais.**
- Les leurres sont **plausibles** : `hex` ICAO d'apparence normale (dérivé de façon déterministe mais sans préfixe reconnaissable), même indicatif/type que l'original. On ne s'appuie donc pas sur l'`hex` pour les reconnaître.
- Le détecteur (INC-5) travaille **sans** la vérité terrain ; elle ne sert qu'à calculer *a posteriori* sa précision/rappel.

## Alternatives envisagées

- **Champ caché `_synthetic` dans le JSON** — écarté : rendrait les faux triviaux à filtrer par quiconque inspecte le flux, biaisant l'évaluation du détecteur.
- **Préfixe d'`hex` reconnaissable** — écarté comme marqueur principal : c'est un signal de détection évident, l'attaque ne serait plus un défi.

## Conséquences

- Positives : attaque fidèle (rien ne trahit les faux dans le signal) ; évaluation rigoureuse du détecteur possible ; démo « révéler » pour la narration.
- Négatives : le proxy doit maintenir cette structure et la synchroniser avec les cibles servies.
- Suivi : INC-5 journalisera la vérité terrain par cycle pour corréler avec les verdicts du détecteur.
