"""V4 — Saturation (DoS d'affichage).

Injecte un grand nombre de cibles fantômes (non liées à un avion réel) autour de
la zone surveillée, pour dégrader l'affichage de la carte et la logique d'alerte.

Les fantômes sont persistants et mobiles (cinématique propre, navigation à
l'estime), avec des indicatifs plausibles. Vérité terrain : marqués `ghost`.

transform(targets, params, ctx) -> (targets, events)
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

# État cinématique des fantômes : hex -> {lat,lon,track,gs,last}.
_ghosts: dict[str, dict] = {}

MAX = 500  # garde-fou


def _center(targets, real_hexes):
    pts = [(t["lat"], t["lon"]) for t in targets
           if t.get("hex") in real_hexes and t.get("lat") is not None]
    if not pts:
        return 43.6777, -79.6248   # repli : station CYYZ
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def transform(targets: list[dict[str, Any]], params: dict, ctx: dict):
    count = min(int(params.get("count", 60)), MAX)
    spread = float(params.get("spread_deg", 0.5))
    now = ctx.get("now")
    real_hexes = ctx.get("real_hexes") or set()
    clat, clon = _center(targets, real_hexes)

    taken = {t.get("hex") for t in targets}
    events = []
    alive = set()
    for i in range(count):
        seed = int(hashlib.md5(f"ghost:{i}".encode()).hexdigest(), 16)
        rnd = random.Random(seed)
        ghex = hashlib.md5(f"ghost:{i}:hex".encode()).hexdigest()[:6]
        if ghex in taken:
            continue
        taken.add(ghex)
        alive.add(ghex)
        st = _ghosts.get(ghex)
        if st is None:
            st = {
                "lat": clat + rnd.uniform(-spread, spread),
                "lon": clon + rnd.uniform(-spread, spread),
                "track": rnd.uniform(0, 360),
                "gs": rnd.uniform(150, 480),
                "flight": "GH" + format(rnd.randint(0, 9999), "04d"),
                "last": now,
            }
            _ghosts[ghex] = st
        else:
            dt = max(0.0, min(now - st["last"], 10.0))
            dist_nm = st["gs"] / 3600.0 * dt
            st["lat"] += dist_nm / 60.0 * math.cos(math.radians(st["track"]))
            st["lon"] += (dist_nm / 60.0 * math.sin(math.radians(st["track"]))) \
                / max(math.cos(math.radians(st["lat"])), 0.1)
            st["last"] = now
        targets.append({
            "hex": ghex,
            "flight": st["flight"],
            "lat": round(st["lat"], 6),
            "lon": round(st["lon"], 6),
            "alt_baro": 30000,
            "gs": round(st["gs"], 1),
            "track": round(st["track"], 1),
            "seen": 0,
        })
        events.append({"hex": ghex, "kind": "ghost"})

    for h in list(_ghosts):
        if h not in alive and now - _ghosts[h]["last"] > 30:
            del _ghosts[h]

    return targets, events
