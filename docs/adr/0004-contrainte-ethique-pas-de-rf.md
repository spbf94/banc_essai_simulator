# ADR-0004 — Vase clos, aucune émission RF réelle

- **Statut :** Accepté
- **Date :** 2026-11-08
- **Décideurs :** Auteur(s)

## Contexte

Les attaques ADS-B étudiées [1]–[3] impliquent en théorie l'émission de signaux sur 1090 MHz. Émettre sur une bande aéronautique réelle est illégal, dangereux pour la sécurité aérienne et hors du périmètre de ce projet. Les travaux de référence eux-mêmes opèrent en laboratoire fermé.

## Décision

Toutes les expérimentations restent **en vase clos, au niveau des données décodées**. Le banc n'émet **aucun signal radiofréquence**. L'injection se fait exclusivement par l'émulateur de récepteur (ADR-0003). Aucun artefact du projet n'est publié en ligne sans accord explicite.

## Alternatives envisagées

- **Transmission RF en cage de Faraday** — écarté pour cette itération : matériel, coût et encadrement non disponibles ; proposé comme amélioration future.

## Conséquences

- Positives : conformité légale et sécuritaire ; reproductibilité ; aucun risque pour le trafic réel.
- Négatives : la couche physique (brouillage, collisions de trames) n'est pas évaluée.
- Suivi : énoncer explicitement cette portée dans la proposition et le rapport ; suggestion d'amélioration = banc RF confiné.
