"""V5 — Attaque ciblée sur un aéronef précis (inspirée de l'approche avionphantom).

Contrairement aux attaques V1-V4 qui s'appliquent à tout le trafic, V5 se
concentre sur UN avion choisi (par `hex` ou indicatif) et falsifie, dans le flux
servi à co-atc, soit son environnement soit sa propre trajectoire. Tout reste en
simulation locale : on altère l'image affichée par co-atc, aucun aéronef réel
n'est touché (ADR-0004).

Deux effets combinables (paramètre `mode`) :
  - "ghost_frontal"  : injecte un aéronef fantôme sur une route de collision
                       frontale, projeté devant la cible puis se rapprochant ;
  - "forced_landing" : prend le contrôle de la trajectoire AFFICHÉE de la cible
                       et la fait descendre en virant vers l'aéroport, comme si
                       elle était contrainte d'atterrir ;
  - "both"           : les deux à la fois.

transform(targets, params, ctx) -> (targets, events)
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

# États cinématiques persistants, par hex de cible.
_ghost_state: dict[str, dict] = {}   # ghost associé à une cible
_descent_state: dict[str, dict] = {}  # descente forcée d'une cible

KT_TO_MS = 0.514444
M_PER_DEG_LAT = 111_132.0


def _m_per_deg_lon(lat: float) -> float:
    return max(111_320.0 * math.cos(math.radians(lat)), 1.0)


def _find_target(targets: list[dict], sel: str):
    """Trouve la cible par hex (exact) puis par indicatif (insensible casse/espaces)."""
    sel = (sel or "").strip().lower()
    if not sel:
        return None
    for t in targets:
        if (t.get("hex") or "").strip().lower() == sel:
            return t
    for t in targets:
        if (t.get("flight") or "").strip().lower() == sel:
            return t
    return None


def _ghost_hex(target_hex: str) -> str:
    return "f5" + hashlib.md5(f"ghost:{target_hex}".encode()).hexdigest()[:4]


def _bearing(lat1, lon1, lat2, lon2) -> float:
    """Cap initial (degrés) de (lat1,lon1) vers (lat2,lon2)."""
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.cos(math.radians(lon2 - lon1)))
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _advance(lat, lon, track, gs_kt, dt):
    """Avance une position par navigation à l'estime."""
    dist_m = gs_kt * KT_TO_MS * dt
    nlat = lat + (dist_m * math.cos(math.radians(track))) / M_PER_DEG_LAT
    nlon = lon + (dist_m * math.sin(math.radians(track))) / _m_per_deg_lon(lat)
    return nlat, nlon


def transform(targets: list[dict[str, Any]], params: dict, ctx: dict):
    sel = params.get("target", "")
    mode = str(params.get("mode", "ghost_frontal"))
    lead_time = float(params.get("lead_time_s", 45))
    descent_fpm = float(params.get("descent_fpm", 2500))
    turn_rate = float(params.get("turn_rate_deg_s", 3.0))
    airport_lat = float(params.get("airport_lat", 43.6777))   # CYYZ par défaut
    airport_lon = float(params.get("airport_lon", -79.6248))
    now = ctx.get("now")
    real_hexes = ctx.get("real_hexes") or set()

    target = _find_target(targets, sel)
    events: list[dict] = []
    if target is None or target.get("lat") is None or target.get("lon") is None:
        return targets, events   # cible absente ce cycle : no-op

    thex = (target.get("hex") or "").lower()
    tlat = float(target["lat"])
    tlon = float(target["lon"])
    ttrack = float(target["track"]) if target.get("track") is not None else 90.0
    tgs = float(target["gs"]) if target.get("gs") is not None else 420.0
    talt = target.get("alt_baro")
    talt = float(talt) if isinstance(talt, (int, float)) else 30000.0

    # ---- Ghost frontal ----
    if mode in ("ghost_frontal", "both"):
        g = _ghost_state.get(thex)
        if g is None:
            v_ms = tgs * KT_TO_MS
            ahead = lead_time * v_ms
            glat = tlat + (ahead * math.cos(math.radians(ttrack))) / M_PER_DEG_LAT
            glon = tlon + (ahead * math.sin(math.radians(ttrack))) / _m_per_deg_lon(tlat)
            g = {"lat": glat, "lon": glon, "track": (ttrack + 180.0) % 360.0,
                 "gs": tgs, "last": now}
            _ghost_state[thex] = g
        else:
            dt = max(0.0, min(now - g["last"], 10.0))
            g["lat"], g["lon"] = _advance(g["lat"], g["lon"], g["track"], g["gs"], dt)
            g["last"] = now
        ghex = _ghost_hex(thex)
        ac = dict(target)
        ac.update({"hex": ghex, "flight": "GHOST" + thex[:3].upper(),
                   "lat": round(g["lat"], 6), "lon": round(g["lon"], 6),
                   "track": round(g["track"], 1), "gs": round(g["gs"], 1),
                   "alt_baro": round(talt), "seen": 0})
        targets.append(ac)
        events.append({"hex": ghex, "kind": "ghost", "clone_of": thex})
    else:
        _ghost_state.pop(thex, None)

    # ---- Atterrissage forcé (contrôle de la trajectoire affichée de la cible) ----
    if mode in ("forced_landing", "both"):
        st = _descent_state.get(thex)
        if st is None:
            st = {"lat": tlat, "lon": tlon, "track": ttrack,
                  "gs": tgs, "alt": talt, "last": now}
            _descent_state[thex] = st
        else:
            dt = max(0.0, min(now - st["last"], 10.0))
            st["last"] = now
            # Vire vers l'aéroport
            brg = _bearing(st["lat"], st["lon"], airport_lat, airport_lon)
            diff = (brg - st["track"] + 540.0) % 360.0 - 180.0
            step = max(-turn_rate * dt, min(turn_rate * dt, diff))
            st["track"] = (st["track"] + step) % 360.0
            # Descente
            st["alt"] = max(0.0, st["alt"] - descent_fpm * (dt / 60.0))
            # Ralentit en approche finale
            if st["alt"] < 3000:
                st["gs"] = max(140.0, st["gs"] - 5.0 * dt)
            st["lat"], st["lon"] = _advance(st["lat"], st["lon"], st["track"], st["gs"], dt)
        # Override des champs affichés de la cible
        on_ground = st["alt"] <= 1.0
        target["lat"] = round(st["lat"], 6)
        target["lon"] = round(st["lon"], 6)
        target["track"] = round(st["track"], 1)
        target["gs"] = round(st["gs"], 1)
        target["alt_baro"] = "ground" if on_ground else round(st["alt"])
        target["baro_rate"] = 0 if on_ground else -int(descent_fpm)
        events.append({"hex": thex, "kind": "spoofed_pos"})
    else:
        _descent_state.pop(thex, None)

    # Purge des états dont la cible a disparu du flux.
    for store in (_ghost_state, _descent_state):
        for h in list(store):
            if h not in real_hexes and now - store[h]["last"] > 30:
                del store[h]

    return targets, events
