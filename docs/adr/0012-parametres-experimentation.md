# ADR-0012 — Paramètres d'expérimentation des attaques

- **Statut :** Accepté
- **Date :** 2026-11-09
- **Décideurs :** Auteur(s)
- **Lié à :** INC-3/INC-4, ADR-0005, ADR-0011

## Contexte

Les attaques doivent être pilotables et reproductibles pour l'expérimentation et la démo. Il faut fixer les paramètres exposés et leurs valeurs par défaut.

## Décision

Paramètres par attaque, réglables à chaud via l'UI (`POST /api/attack/{key}/params`) :

| Attaque | Paramètres | Défaut |
|---------|-----------|--------|
| V1 clonage | `n` (leurres/avion), `trajectory_mode` (`divergent`/`parallel`), `pos_jitter_deg`, `heading_spread_deg`, `gs_jitter`, `turn_rate_deg_s` | 3, divergent, 0.02, 90, 0.25, 2.0 |
| V2 trajectoire | `count` (avions ciblés, 0=tous), `drift_kt` | 1, 150 |
| V3 squawk | `code` (7500/7600/7700), `count` | 7700, 1 |
| V4 flood | `count` (fantômes), `spread_deg` | 60, 0.5 |

`trajectory_mode` permet de comparer leurres **divergents** (cinématique propre) et **parallèles** (décalage fixe) — utile pour montrer l'intérêt de la divergence.

## Conséquences

- Positives : expériences variées et reproductibles ; démonstration comparative.
- Négatives : un garde-fou limite le flood (`MAX=500`) pour éviter de saturer la machine.
- Suivi : INC-5 fera varier ces paramètres pour mesurer la robustesse du détecteur.
