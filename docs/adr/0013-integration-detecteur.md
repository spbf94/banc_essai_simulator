# ADR-0013 — Intégration du détecteur de défense

- **Statut :** Accepté
- **Date :** 2026-11-09
- **Décideurs :** Auteur(s)
- **Met en œuvre :** ADR-0006 (défense), ADR-0011 (vérité terrain)

## Contexte

Le détecteur D1/D2 doit être intégré sans modifier co-atc ni le proxy, et son évaluation ne doit jamais utiliser la vérité terrain comme entrée de décision.

## Décision

Le détecteur vit dans un dossier séparé **`defense/`** (Python autonome, aucune dépendance au cœur co-atc ni à l'interface du proxy).

- **Point de prélèvement** : le détecteur consomme les mêmes données que co-atc (les cibles du flux `aircraft.json`), avec un historique glissant par `hex`. Il note chaque piste **sans** vérité terrain.
- **Évaluation séparée** : le harnais `defense/evaluate.py` importe le pipeline d'attaques (`from attacks import apply_pipeline` via `../attack-proxy`), rejoue `data/sample_replay.json`, et n'utilise la sortie « truth » (ADR-0011) que pour le calcul *a posteriori* des métriques. La vérité terrain ne conditionne aucune décision du détecteur.
- **Horloge** : les horodatages réels sont reconstitués depuis `data/*.db` (le JSON de rejeu ne porte pas le temps), nécessaires à la cinématique ; le moteur d'attaques n'est pas modifié.

## Alternatives envisagées

- **Détecteur intégré dans co-atc** — écarté : modifierait le cœur ; la comparaison avant/après est plus nette en module externe.
- **Détecteur lisant `/api/truth`** — écarté : fausserait l'évaluation (il « connaîtrait » les réponses).

## Conséquences

- Positives : séparation stricte, évaluation honnête, co-atc et proxy intacts.
- Négatives : le détecteur reconstitue l'historique côté lui (état par `hex`) ; dépend de la qualité temporelle du rejeu.
- Suivi : seuils D1/D2 figés dans `defense/` ; piste D3 (MLAT) non implémentée (un seul récepteur).
