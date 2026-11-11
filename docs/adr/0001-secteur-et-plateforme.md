# ADR-0001 — Secteur aéronautique et plateforme Co-ATC

- **Statut :** Accepté
- **Date :** 2026-11-08
- **Décideurs :** Auteur(s)

## Contexte

Le projet impose de choisir une infrastructure critique et de bâtir un banc d'essai de cybersécurité à partir de l'existant (articles de référence, open source). Le secteur aéronautique est retenu pour le projet, avec cinq articles fournis portant sur la sécurité de l'ADS-B [1]–[5].

## Décision

Étudier la **surveillance coopérative ADS-B** et utiliser **Co-ATC** (`github.com/yegors/co-atc`, licence MIT) comme système sous test. Co-ATC est une chaîne de supervision ATC réelle : ingestion ADS-B, reconstruction de trajectoires, détection de phases et de conflits, carte temps réel.

## Alternatives envisagées

- **Écrire notre propre récepteur/afficheur** — écarté : réinvente l'existant ; l'approche retenue consiste à partir de l'existant.
- **Simulateur de trafic seul (type [5])** — écarté : ne met aucun logiciel de supervision réel à l'épreuve.

## Conséquences

- Positives : SUT réaliste et complet ; données et carte exploitables pour la démo.
- Négatives : dépendance à un code tiers « généré par IA, sans revue de sécurité » (README) — à documenter comme hypothèse.
- Suivi : limite à deux équipes par secteur (premier arrivé) ; confirmer la réservation du secteur aéronautique.
