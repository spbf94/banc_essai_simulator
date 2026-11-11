"""V2 — Spoofing de trajectoire d'un aéronef légitime.

Fait dériver progressivement la position RÉELLE d'un ou plusieurs avions (l'avion
semble s'écarter de sa vraie route). La dérive est cumulative dans le temps, selon
un cap propre à chaque avion ciblé.

Vérité terrain : chaque avion dont la position est falsifiée est marqué
`spoofed_pos` (ce n'est pas un faux avion, mais une fausse position).

transform(targets, params, ctx) -> (targets, events)
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

# Dérive cumulative par hex : {dlat, dlon, bearing, last}.
_drift: dict[str, dict] = {}


def transform(targets: list[dict[str, Any]], params: dict, ctx: dict):
    count = int(params.get("count", 1))           # 0 = tous les avions réels
    drift_kt = float(params.get("drift_kt", 150))  # vitesse de dérive apparente
    now = ctx.get("now")
    real_hexes = ctx.get("real_hexes") or set()

    # Avions réels avec position, ordre déterministe.
    reals = [t for t in targets
             if t.get("hex") in real_hexes and t.get("lat") is not None]
    reals.sort(key=lambda t: t.get("hex", ""))
    if count > 0:
        reals = reals[:count]

    events = []
    for t in reals:
        hx = t["hex"]
        st = _drift.get(hx)
        if st is None:
            seed = int(hashlib.md5(f"{hx}:drift".encode()).hexdigest(), 16)
            bearing = random.Random(seed).uniform(0, 360)
            st = {"dlat": 0.0, "dlon": 0.0, "bearing": bearing, "last": now}
            _drift[hx] = st
        dt = max(0.0, min(now - st["last"], 10.0))
        st["last"] = now
        step_nm = drift_kt / 3600.0 * dt
        st["dlat"] += step_nm / 60.0 * math.cos(math.radians(st["bearing"]))
        st["dlon"] += (step_nm / 60.0 * math.sin(math.radians(st["bearing"]))) \
            / max(math.cos(math.radians(t["lat"])), 0.1)
        t["lat"] = round(t["lat"] + st["dlat"], 6)
        t["lon"] = round(t["lon"] + st["dlon"], 6)
        events.append({"hex": hx, "kind": "spoofed_pos"})

    # Purge des dérives pour des avions disparus.
    for h in list(_drift):
        if h not in real_hexes and now - _drift[h]["last"] > 30:
            del _drift[h]

    return targets, events
