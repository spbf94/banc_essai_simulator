# ADR-0014 — Attaque ciblée V5 (avion fantôme / atterrissage forcé)

- **Statut :** Accepté
- **Date :** 2026-11-09
- **Décideurs :** Auteur(s)
- **Inspiré de :** approche alternative `avionphantom` (radar TCP + bridge readsb)

## Contexte

Les attaques V1–V4 s'appliquent à l'ensemble du trafic. Une approche alternative explorée en parallèle (`avionphantom`) propose un scénario plus narratif : viser **un avion précis**, lui opposer un aéronef fantôme en collision frontale, et illustrer une manœuvre d'évitement / un atterrissage. On veut intégrer cette idée au banc existant, pilotable depuis la même UI, sans changer de transport (on reste en HTTP `readsb-api`, pas en socket TCP Beast).

## Décision

Ajouter une attaque **V5 ciblée** (`attacks/v5_targeted.py`) dans le pipeline du proxy. Elle prend un paramètre **`target`** (hex ou indicatif) et un **`mode`** :

- **`ghost_frontal`** : injecte un aéronef fantôme projeté `lead_time_s` (45 s) devant la cible, sur le cap opposé, se rapprochant par navigation à l'estime → conflit frontal sur l'avion visé.
- **`forced_landing`** : prend le contrôle de la **trajectoire affichée** de la cible (état cinématique propre) et la fait **descendre** (`descent_fpm`) en **virant vers l'aéroport** (`airport_lat/lon`, CYYZ par défaut), jusqu'à « atterrir ».
- **`both`** : les deux.

Paramètres réglables depuis l'UI (sélecteur d'avion peuplé par les avions réels courants). Vérité terrain : le fantôme est marqué `ghost` (lié à la cible via `clone_of`), la cible falsifiée est marquée `spoofed_pos`.

Tout reste en **simulation locale** : on altère uniquement l'image affichée par co-atc ; aucun aéronef réel n'est affecté (ADR-0004).

## Alternatives envisagées

- **Reprendre le transport TCP + readsb-file de `avionphantom`** — écarté : on garde l'intégration HTTP unique (ADR-0007) et l'UI existante ; on ne réimporte que les *concepts*.
- **Faire manœuvrer réellement la cible** — impossible et hors sujet : la cible est un aéronef réel du flux amont ; on ne falsifie que ce que co-atc affiche.

## Conséquences

- Positives : démo ciblée et parlante (conflit frontal, descente forcée sur un vol nommé) ; réutilise le moteur, l'UI, la vérité terrain et le détecteur existants.
- Négatives : en `forced_landing`, la position affichée se détache de la position réelle amont (c'est l'effet voulu) ; le détecteur D1 doit alors traiter cette incohérence.
- Suivi : le détecteur (defense/) pourra être évalué sur V5 (fantôme + téléportation/descente incohérente de la cible).
