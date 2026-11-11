"""V1 — Clonage d'aéronefs (attaque phare, ADR-0005).

Pour chaque avion réel, on produit N leurres portant le MÊME indicatif et le
même type, mais ayant chacun sa PROPRE trajectoire, de sorte que les leurres
divergent de l'original et les uns des autres (pas de trajectoires parallèles).

Chaque leurre a un état cinématique persistant (lat, lon, cap, vitesse, taux de
virage) propagé par navigation à l'estime à chaque cycle :
  - à sa création : position proche de l'original, mais cap et vitesse décalés
    aléatoirement, plus un léger taux de virage propre → trajectoire divergente ;
  - ensuite : il avance selon SON cap, indépendamment de l'original.

Les leurres restent plausibles : hex ICAO d'apparence normale (ADR-0011) ; on ne
les reconnaît que via la vérité terrain hors-bande, pas via l'hex.

transform(targets, params) -> (nouvelles_cibles, leurres)
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from typing import Any

# État cinématique persistant des leurres : hex -> {lat,lon,track,gs,turn,last}.
_clones: dict[str, dict] = {}


def _clone_hex(real_hex: str, i: int, taken: set) -> str:
    base = hashlib.md5(f"{real_hex}:{i}".encode()).hexdigest()[:6]
    h, bump = base, 0
    while h in taken:
        bump += 1
        h = hashlib.md5(f"{real_hex}:{i}:{bump}".encode()).hexdigest()[:6]
    return h


def _parallel_offset(real_hex: str, i: int, pos_jitter: float):
    """Décalage fixe déterministe (mode parallèle : le leurre translate comme l'original)."""
    seed = int(hashlib.md5(f"{real_hex}:{i}:par".encode()).hexdigest(), 16)
    rnd = random.Random(seed)
    return rnd.uniform(-pos_jitter, pos_jitter), rnd.uniform(-pos_jitter, pos_jitter)


def transform(targets: list[dict[str, Any]], params: dict, ctx: dict):
    n = int(params.get("n", 3))
    pos_jitter = float(params.get("pos_jitter_deg", 0.02))     # écart initial
    heading_spread = float(params.get("heading_spread_deg", 90))  # divergence des caps
    gs_jitter = float(params.get("gs_jitter", 0.25))           # ±25 % de vitesse
    turn_max = float(params.get("turn_rate_deg_s", 2.0))       # courbure aléatoire
    mode = str(params.get("trajectory_mode", "divergent"))     # "divergent" | "parallel"

    now = ctx.get("now", time.time())
    real_hexes = ctx.get("real_hexes") or {t.get("hex") for t in targets}
    out = list(targets)                       # les réels restent inchangés
    taken = {t.get("hex") for t in targets}
    events: list[dict] = []
    alive: set[str] = set()

    for t in targets:
        if t.get("hex") not in real_hexes:    # ne clone que les avions réels
            continue
        if t.get("lat") is None or t.get("lon") is None:
            continue
        for i in range(n):
            chex = _clone_hex(t["hex"], i, taken)
            taken.add(chex)
            alive.add(chex)

            if mode == "parallel":
                # Décalage fixe : le leurre suit l'original, trajectoires parallèles.
                dlat, dlon = _parallel_offset(t["hex"], i, pos_jitter)
                c = dict(t)
                c["hex"] = chex
                c["lat"] = round(t["lat"] + dlat, 6)
                c["lon"] = round(t["lon"] + dlon, 6)
                out.append(c)
                events.append({"hex": chex, "kind": "clone", "clone_of": t.get("hex")})
                continue

            st = _clones.get(chex)

            if st is None:
                # Initialisation déterministe mais divergente.
                seed = int(hashlib.md5(f"{t['hex']}:{i}:init".encode()).hexdigest(), 16)
                rnd = random.Random(seed)
                base_track = float(t["track"]) if t.get("track") is not None else rnd.uniform(0, 360)
                base_gs = float(t["gs"]) if t.get("gs") is not None else 300.0
                st = {
                    "lat": t["lat"] + rnd.uniform(-pos_jitter, pos_jitter),
                    "lon": t["lon"] + rnd.uniform(-pos_jitter, pos_jitter),
                    "track": (base_track + rnd.uniform(-heading_spread, heading_spread)) % 360,
                    "gs": max(60.0, base_gs * (1 + rnd.uniform(-gs_jitter, gs_jitter))),
                    "turn": rnd.uniform(-turn_max, turn_max),
                    "alt": t.get("alt_baro"),
                    "last": now,
                }
                _clones[chex] = st
            else:
                # Navigation à l'estime selon le cap propre du leurre.
                dt = max(0.0, min(now - st["last"], 10.0))
                st["track"] = (st["track"] + st["turn"] * dt) % 360
                dist_nm = st["gs"] / 3600.0 * dt                 # nœuds -> nm sur dt
                dlat = dist_nm / 60.0 * math.cos(math.radians(st["track"]))
                dlon = (dist_nm / 60.0 * math.sin(math.radians(st["track"]))) \
                    / max(math.cos(math.radians(st["lat"])), 0.1)
                st["lat"] += dlat
                st["lon"] += dlon
                st["last"] = now

            c = dict(t)                        # même indicatif, type, etc.
            c["hex"] = chex
            c["lat"] = round(st["lat"], 6)
            c["lon"] = round(st["lon"], 6)
            c["track"] = round(st["track"], 1)
            c["gs"] = round(st["gs"], 1)
            if isinstance(st.get("alt"), (int, float)):
                c["alt_baro"] = st["alt"]
            out.append(c)
            events.append({"hex": chex, "kind": "clone", "clone_of": t.get("hex")})

    # Purge des états de leurres qui ne sont plus produits (attaque coupée, avion parti).
    for h in list(_clones):
        if h not in alive and now - _clones[h]["last"] > 30:
            del _clones[h]

    return out, events
