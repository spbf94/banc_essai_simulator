"""Moteur d'attaques — pipeline de transformations.

INC-1 : le pipeline est l'identité (pass-through). Chaque attaque viendra
s'ajouter comme une fonction `transform(targets, params) -> targets`
activable via l'état partagé, aux incréments suivants :

  - v1_clone      (INC-3)  : duplique chaque avion réel en N leurres
  - v2_trajectory (INC-4)  : fait dériver la position d'un leurre
  - v3_squawk     (INC-4)  : injecte un squawk d'urgence
  - v4_flood      (INC-4)  : sature de cibles

L'ordre d'application sera défini ici quand les transformations existeront.
"""

from __future__ import annotations

from typing import Any

# Métadonnées des attaques (pour l'UI de pilotage).
# "implemented" passera à True au fur et à mesure (INC-3 pour V1, INC-4 pour le reste).
ATTACK_INFO = [
    {
        "key": "v1_clone",
        "label": "Clonage d'aéronefs",
        "flagship": True,
        "implemented": True,
        "desc": ("Duplique chaque avion réel en N leurres portant le même indicatif. "
                 "Chaque leurre suit sa propre trajectoire divergente (cap et vitesse "
                 "aléatoires) : on ne distingue plus le vrai avion de ses copies."),
    },
    {
        "key": "v2_trajectory",
        "label": "Spoofing de trajectoire",
        "flagship": False,
        "implemented": True,
        "desc": ("Fait dériver progressivement la position réelle d'un avion "
                 "légitime, qui semble alors s'écarter de sa vraie route."),
    },
    {
        "key": "v3_squawk",
        "label": "Faux squawk d'urgence",
        "flagship": False,
        "implemented": True,
        "desc": ("Injecte un code transpondeur d'urgence : 7500 (détournement), "
                 "7600 (panne radio) ou 7700 (urgence générale)."),
        "controls": [
            {"param": "code", "label": "Code", "type": "select",
             "options": ["7700", "7600", "7500"]},
        ],
    },
    {
        "key": "v4_flood",
        "label": "Saturation (DoS d'affichage)",
        "flagship": False,
        "implemented": True,
        "desc": ("Injecte de nombreuses cibles fantômes pour dégrader l'affichage "
                 "de la carte et la logique d'alerte de co-atc."),
    },
    {
        "key": "v5_targeted",
        "label": "Attaque ciblée (avion fantôme / atterrissage forcé)",
        "flagship": False,
        "implemented": True,
        "desc": ("Vise un avion précis. « Ghost frontal » : injecte un fantôme en "
                 "collision frontale sur sa route. « Atterrissage forcé » : prend le "
                 "contrôle de sa trajectoire affichée et la fait descendre vers "
                 "l'aéroport."),
        "controls": [
            {"param": "target", "label": "Avion cible", "type": "target"},
            {"param": "mode", "label": "Effet", "type": "select",
             "options": ["ghost_frontal", "forced_landing", "both"]},
        ],
    },
]

# Contrôle de trajectoire pour V1 (divergente/parallèle), ajouté à sa carte.
ATTACK_INFO[0]["controls"] = [
    {"param": "trajectory_mode", "label": "Trajectoires", "type": "select",
     "options": ["divergent", "parallel"]},
]

import time

from . import v1_clone, v2_trajectory, v3_squawk, v4_flood, v5_targeted

# Registre des transformations (clé -> fonction). L'ordre d'application compte :
# cloner d'abord les avions réels pristine, puis falsifier/saturer, puis le ciblé.
REGISTRY: dict = {
    "v1_clone": v1_clone.transform,
    "v2_trajectory": v2_trajectory.transform,
    "v3_squawk": v3_squawk.transform,
    "v4_flood": v4_flood.transform,
    "v5_targeted": v5_targeted.transform,
}
ORDER = ["v1_clone", "v2_trajectory", "v3_squawk", "v4_flood", "v5_targeted"]


def apply_pipeline(targets: list[dict[str, Any]], attacks):
    """Applique les attaques activées et renvoie (cibles_servies, verite_terrain).

    Chaque transform renvoie (cibles, events), event = {hex, kind, ...} avec kind
    ∈ {clone, ghost, spoofed_pos, spoofed_squawk}. La vérité terrain reste
    hors-bande (ADR-0011) : co-atc ne reçoit que les cibles.
    """
    now = time.time()
    real_hexes = {t.get("hex") for t in targets}
    ctx = {"now": now, "real_hexes": real_hexes}

    result = targets
    synthetic: dict = {}   # faux avions (clones + fantômes)
    spoofed: dict = {}     # avions réels falsifiés (position / squawk)

    for key in ORDER:
        fn = REGISTRY.get(key)
        if fn and attacks.enabled.get(key):
            result, events = fn(result, attacks.params.get(key, {}), ctx)
            for e in events:
                if e["kind"] in ("clone", "ghost"):
                    synthetic[e["hex"]] = {"attack": key, "kind": e["kind"],
                                           "clone_of": e.get("clone_of")}
                else:
                    spoofed[e["hex"]] = {"attack": key, "kind": e["kind"],
                                         "code": e.get("code")}

    return result, {
        "synthetic": synthetic, "spoofed": spoofed,
        "synthetic_count": len(synthetic), "spoofed_count": len(spoofed),
        # Liste des hex réels (en plus du compte) : nécessaire à la
        # journalisation de la vérité terrain par cycle (truth_log, INC-5).
        "real_hexes": sorted(h for h in real_hexes if h),
        "real_count": len(real_hexes), "served_count": len(result),
    }
