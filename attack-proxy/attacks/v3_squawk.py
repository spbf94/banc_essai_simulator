"""V3 — Faux squawk d'urgence.

Injecte un code transpondeur d'urgence sur un ou plusieurs avions réels :
  7500 = détournement, 7600 = panne radio, 7700 = urgence générale.

Vérité terrain : chaque avion dont le squawk est falsifié est marqué
`spoofed_squawk`.

transform(targets, params, ctx) -> (targets, events)
"""

from __future__ import annotations

from typing import Any

VALID = {"7500", "7600", "7700"}


def transform(targets: list[dict[str, Any]], params: dict, ctx: dict):
    code = str(params.get("code", "7700"))
    if code not in VALID:
        code = "7700"
    count = int(params.get("count", 1))           # 0 = tous les avions réels
    real_hexes = ctx.get("real_hexes") or set()

    reals = [t for t in targets if t.get("hex") in real_hexes]
    reals.sort(key=lambda t: t.get("hex", ""))
    if count > 0:
        reals = reals[:count]

    events = []
    for t in reals:
        t["squawk"] = code
        t["emergency"] = {"7500": "hijack", "7600": "nordo", "7700": "general"}[code]
        events.append({"hex": t["hex"], "kind": "spoofed_squawk", "code": code})

    return targets, events
