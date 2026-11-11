# ADR-0006 — Défense : détecteur de plausibilité

- **Statut :** Accepté
- **Date :** 2026-11-08 (accepté le 2026-11-09 après validation du prototype)
- **Décideurs :** Auteur(s)

## Contexte

Le projet vise une proposition de remédiation idéalement démontrable. Co-ATC contient déjà `internal/physics/physics.go` et une prédiction de trajectoire, réutilisables.

## Décision (proposée)

Ajouter un **module de défense séparé** qui attribue à chaque piste un score de confiance via deux familles de contrôles :

- **D1 — Plausibilité cinématique** : bornes de vitesse/accélération/taux de montée, sauts de position incompatibles avec la vitesse max, cohérence cap/vecteur.
- **D2 — Cohérence des métadonnées** : indicatif dupliqué à plusieurs positions, adresse ICAO « téléportée », champs d'intégrité (`NIC/NAC/SIL`) et `RSSI` uniformes/incohérents.

La MLAT/TDOA multi-récepteurs (D3) est **discutée mais non implémentée** (récepteur unique).

## Alternatives envisagées

- **Détection purement statistique/ML** — écarté pour l'itération : besoin de données d'entraînement, moins explicable en démonstration.
- **Modifier le cœur de Co-ATC** — écarté : garder la défense en module séparé facilite la comparaison avant/après.

## Conséquences

- Positives : remédiation concrète et démontrable ; s'appuie sur du code existant ; explicable à un opérateur.
- Négatives : faux positifs possibles sur manœuvres brusques légitimes ; un attaquant « physiquement cohérent » peut échapper à D1 (d'où l'intérêt de D2/D3).
- Suivi : fixer les seuils ; mesurer précision/rappel sur les scénarios V1–V4 ; passer à `Accepté` une fois le prototype validé.

## Validation (2026-11-09)

Prototype implémenté dans `defense/` (module séparé). Résultats sur 371 trames réelles, F1 : V4 flood 1.00, V3 squawk 0.98, V1 clonage 0.82 (rappel 0.90), V2 trajectoire 0.68 (précision 0.95, rappel 0.53). Faux positifs de base : 0,2 %. Clé D1 : résidu de navigation à l'estime sur **fenêtre glissante 12–30 s** (la vitesse instantanée mono-cycle est du bruit à cause de la quantification ADS-B). Limites confirmées et attendues : V1 sans indicatif échappe à D2 (→ motive D3/MLAT) ; V2 sous le plancher de bruit au début. ADR-0006 **accepté**.
