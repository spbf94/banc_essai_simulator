"""Module de défense du banc d'essai ADS-B (dépôt co-atc).

Détecteur de plausibilité (ADR-0006) en module séparé : il consomme le flux de
pistes servi à co-atc (sortie du proxy d'attaque) et attribue à CHAQUE piste un
score de confiance, SANS jamais recevoir la vérité terrain (ADR-0011).

Deux familles de contrôles :
  - D1 — plausibilité cinématique   (voir detector.py)
  - D2 — cohérence des métadonnées  (voir detector.py)

Rien ici ne dépend de co-atc ni de attack-proxy ; le harnais d'évaluation
(evaluate.py) importe le pipeline d'attaques uniquement pour fabriquer des
données de test et lire la vérité terrain *a posteriori*.
"""

from __future__ import annotations

from .detector import Detector, TrackVerdict

__all__ = ["Detector", "TrackVerdict"]
