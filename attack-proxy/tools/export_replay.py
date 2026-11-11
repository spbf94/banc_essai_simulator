#!/usr/bin/env python3
"""Exporte un fichier de rejeu depuis une base co-atc (data/*.db).

Lit la table `adsb_targets`, regroupe les enregistrements par horodatage
(seconde) en « trames », et écrit un JSON conforme au contrat ADR-0009 :

    { "meta": {...}, "frames": [ { "aircraft": [ {hex,lat,lon,...}, ... ] }, ... ] }

Le proxy (mode replay_file) sert une trame par requête de co-atc, en boucle,
ce qui permet de simuler hors-ligne sans accès aux données live.

Usage :
    python tools/export_replay.py ../data/co-atc-2026-11-09.db \
        -o data/sample_replay.json --max-frames 600
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import OrderedDict

# Colonnes de adsb_targets -> champ du contrat aircraft.json (ADR-0009).
FIELDS = [
    ("hex", "hex"),
    ("flight", "flight"),
    ("aircraft_type", "t"),
    ("lat", "lat"),
    ("lon", "lon"),
    ("alt_baro", "alt_baro"),
    ("alt_geom", "alt_geom"),
    ("gs", "gs"),
    ("track", "track"),
    ("baro_rate", "baro_rate"),
    ("squawk", "squawk"),
    ("messages", "messages"),
    ("rssi", "rssi"),
]


def export(db_path: str, out_path: str, max_frames: int) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cols = ", ".join(c for c, _ in FIELDS) + ", timestamp"
    rows = cur.execute(
        f"SELECT {cols} FROM adsb_targets "
        f"WHERE lat IS NOT NULL AND lon IS NOT NULL "
        f"ORDER BY timestamp ASC"
    )

    frames: "OrderedDict[str, list]" = OrderedDict()
    for r in rows:
        ts = r["timestamp"]
        target = {}
        for col, jkey in FIELDS:
            val = r[col]
            if val is None or val == "":
                continue
            target[jkey] = val
        target["seen"] = 0  # rejoué comme « frais »
        frames.setdefault(ts, []).append(target)

    con.close()

    frame_list = [{"aircraft": ac} for ac in frames.values()]
    if max_frames > 0:
        frame_list = frame_list[:max_frames]

    out = {
        "meta": {
            "source_db": db_path,
            "frames": len(frame_list),
            "total_targets": sum(len(f["aircraft"]) for f in frame_list),
            "note": "rejeu hors-ligne — contrat ADR-0009 ; 1 trame servie par requête",
        },
        "frames": frame_list,
    }
    with open(out_path, "w") as fh:
        json.dump(out, fh)
    print(f"OK: {len(frame_list)} trames, "
          f"{out['meta']['total_targets']} cibles -> {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Export d'un fichier de rejeu co-atc")
    ap.add_argument("db", help="chemin d'une base data/co-atc-*.db")
    ap.add_argument("-o", "--out", default="data/sample_replay.json",
                    help="fichier de rejeu de sortie")
    ap.add_argument("--max-frames", type=int, default=600,
                    help="nombre maximum de trames (0 = toutes)")
    args = ap.parse_args()
    export(args.db, args.out, args.max_frames)
