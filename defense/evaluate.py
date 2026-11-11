#!/usr/bin/env python3
"""Harnais d'évaluation du détecteur de défense (ADR-0006, ADR-0011).

Mesure la précision et le rappel du détecteur contre chaque scénario d'attaque
V1–V4, sur des données fabriquées par le MÊME moteur d'attaques que le proxy.

Principe :
  1. On charge le rejeu hors-ligne `attack-proxy/data/sample_replay.json`
     (régénéré au besoin via `attack-proxy/tools/export_replay.py` depuis
     `data/*.db`).
  2. Pour chaque scénario, on active UNE attaque et on applique le pipeline
     `attacks.apply_pipeline` trame par trame : il renvoie (cibles_servies,
     vérité_terrain).
  3. Le détecteur note les cibles servies SANS voir la vérité terrain.
  4. On compare *a posteriori* les verdicts à la vérité terrain pour calculer
     précision / rappel / F1 par scénario.

Horloge virtuelle : les attaques propagent les leurres par navigation à l'estime
en lisant `time.time()`. En rejeu accéléré, on remplace cette horloge par un
compteur virtuel (+1 s par trame) pour que la cinématique des leurres (et la
dérive V2) évolue de façon réaliste.

Usage :
    python3 defense/evaluate.py
    python3 defense/evaluate.py --frames 200 --dt 1.0
"""

from __future__ import annotations

import argparse
import copy
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PROXY = os.path.join(REPO, "attack-proxy")
REPLAY = os.path.join(PROXY, "data", "sample_replay.json")

# --- Import du moteur d'attaques (module séparé) -------------------------- #
sys.path.insert(0, PROXY)
import json  # noqa: E402

import attacks  # noqa: E402  (attack-proxy/attacks)
from attacks import apply_pipeline, v1_clone, v2_trajectory, v4_flood  # noqa: E402
from state import AttackState  # noqa: E402  (attack-proxy/state.py)

# --- Import du détecteur (ce module-ci) ----------------------------------- #
sys.path.insert(0, REPO)
from defense.detector import Detector, DetectorConfig  # noqa: E402


# --------------------------------------------------------------------------- #
# Horloge virtuelle partagée avec le moteur d'attaques
# --------------------------------------------------------------------------- #

class _VClock:
    """Remplace le module `time` vu par attacks/__init__.py (il n'en utilise
    que `.time()`). Le harnais y pousse l'horodatage réel de chaque trame, de
    sorte que la cinématique des leurres (navigation à l'estime) et la dérive V2
    évoluent avec le temps réellement écoulé entre deux trames."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def time(self) -> float:
        return self.t


# --------------------------------------------------------------------------- #
# Scénarios : une attaque chacun, avec ses paramètres (documentés).
# --------------------------------------------------------------------------- #

SCENARIOS = {
    "V1 clonage": {
        "key": "v1_clone",
        "params": {"n": 3, "pos_jitter_deg": 0.02, "heading_spread_deg": 90,
                   "gs_jitter": 0.25, "turn_rate_deg_s": 2.0,
                   "trajectory_mode": "divergent"},
    },
    "V2 trajectoire": {
        "key": "v2_trajectory",
        "params": {"count": 3, "drift_kt": 150},
    },
    "V3 squawk": {
        "key": "v3_squawk",
        "params": {"code": "7700", "count": 3},
    },
    "V4 flood": {
        "key": "v4_flood",
        "params": {"count": 60, "spread_deg": 0.5},
    },
}


def _reset_attack_state() -> None:
    """Purge l'état cinématique persistant des attaques entre deux scénarios."""
    v1_clone._clones.clear()
    v2_trajectory._drift.clear()
    v4_flood._ghosts.clear()


def _load_frames(max_frames: int, dt: float) -> tuple[list, str]:
    """Renvoie (frames, source), frames = liste de (now, aircraft).

    Source de WHAT (quelles cibles) : le rejeu `sample_replay.json` (régénéré au
    besoin). Source du QUAND (horodatage de chaque trame) : la base co-atc, car
    le JSON ne porte pas les timestamps et la cinématique a besoin du temps réel
    écoulé entre trames. Si la base est absente, on retombe sur un pas de temps
    fixe `dt` (les grands sauts de rejeu peuvent alors gonfler les faux positifs).
    """
    if not os.path.exists(REPLAY):
        _regenerate_replay()
    with open(REPLAY) as fh:
        data = json.load(fh)
    json_frames = [f.get("aircraft", []) for f in data.get("frames", [])]

    stamps = _frame_timestamps(data.get("meta", {}).get("source_db", ""),
                               len(json_frames))
    if stamps is not None:
        frames = list(zip(stamps, json_frames))
        source = "rejeu JSON + horodatage base co-atc"
    else:
        t = 0.0
        frames = []
        for ac in json_frames:
            t += dt
            frames.append((t, ac))
        source = f"rejeu JSON (pas de temps fixe {dt:.0f}s, base absente)"

    if max_frames > 0:
        frames = frames[:max_frames]
    return frames, source


def _frame_timestamps(source_db: str, n_frames: int):
    """Reconstitue l'horodatage epoch de chaque trame en rejouant le même
    regroupement que tools/export_replay.py (GROUP BY timestamp, ordre ASC).
    Renvoie None si la base est introuvable ou illisible."""
    import datetime
    import sqlite3

    cand = source_db
    if cand and not os.path.isabs(cand):
        cand = os.path.normpath(os.path.join(PROXY, cand))
    paths = [cand] if cand and os.path.exists(cand) else []
    if not paths:
        import glob
        paths = sorted(g for g in glob.glob(os.path.join(REPO, "data", "co-atc-*.db"))
                       if not g.endswith(("-wal", "-shm")))
    if not paths:
        return None
    db = paths[-1]
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT DISTINCT timestamp FROM adsb_targets "
            "WHERE lat IS NOT NULL AND lon IS NOT NULL ORDER BY timestamp ASC"
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return None

    def epoch(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return datetime.datetime.fromisoformat(
                str(x).replace("Z", "+00:00")).timestamp()

    stamps = [epoch(r[0]) for r in rows]
    if len(stamps) < n_frames:
        return None
    return stamps[:n_frames]


def _regenerate_replay() -> None:
    """Régénère le rejeu depuis la base co-atc la plus récente."""
    import glob
    dbs = sorted(glob.glob(os.path.join(REPO, "data", "co-atc-*.db")))
    dbs = [d for d in dbs if not d.endswith(("-wal", "-shm"))]
    if not dbs:
        raise SystemExit("Aucune base data/co-atc-*.db pour régénérer le rejeu.")
    db = dbs[-1]
    tool = os.path.join(PROXY, "tools", "export_replay.py")
    print(f"[harnais] rejeu absent -> régénération depuis {os.path.basename(db)}")
    subprocess.run([sys.executable, tool, db, "-o", REPLAY, "--max-frames", "600"],
                   check=True, cwd=PROXY)


# --------------------------------------------------------------------------- #
# Évaluation d'un scénario
# --------------------------------------------------------------------------- #

def eval_scenario(name: str, spec: dict, frames: list[list[dict]],
                  dt: float, cfg: DetectorConfig) -> dict:
    """Déroule un scénario et renvoie les métriques (par instance de piste)."""
    _reset_attack_state()
    detector = Detector(cfg)

    clock = _VClock()
    attacks.time = clock  # type: ignore  (attacks n'utilise que time.time())

    state = AttackState()
    if spec["key"] is not None:
        state.enabled[spec["key"]] = True
        state.params[spec["key"]].update(spec["params"])

    tp = fp = fn = tn = 0
    reason_counts: dict[str, int] = {}
    served_total = synth_total = spoof_total = 0

    for now, frame in frames:
        clock.t = now
        base = copy.deepcopy(frame)                 # les attaques mutent en place
        served, truth = apply_pipeline(base, state)

        positives = set(truth.get("synthetic", {})) | set(truth.get("spoofed", {}))
        synth_total += len(truth.get("synthetic", {}))
        spoof_total += len(truth.get("spoofed", {}))
        served_total += len(served)

        verdicts = detector.score_frame(served, now)

        for ac in served:
            hx = ac.get("hex")
            v = verdicts.get(hx)
            flagged = bool(v and v.flagged)
            is_pos = hx in positives
            if flagged and is_pos:
                tp += 1
            elif flagged and not is_pos:
                fp += 1
            elif (not flagged) and is_pos:
                fn += 1
            else:
                tn += 1
            if flagged and v:
                for code, _ in v.reasons:
                    reason_counts[code] = reason_counts.get(code, 0) + 1

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = (2 * precision * recall / (precision + recall)
          if (tp + fp) and (tp + fn) and (precision + recall) else float("nan"))

    return {
        "name": name, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "positives": tp + fn, "served": served_total,
        "synthetic": synth_total, "spoofed": spoof_total,
        "reasons": reason_counts,
    }


def eval_baseline(frames: list[list[dict]], dt: float, cfg: DetectorConfig) -> dict:
    """Aucune attaque : toute alarme est un faux positif (manœuvres légitimes)."""
    _reset_attack_state()
    detector = Detector(cfg)
    clock = _VClock()
    attacks.time = clock  # type: ignore
    state = AttackState()  # tout désactivé

    flags = total = 0
    reason_counts: dict[str, int] = {}
    for now, frame in frames:
        clock.t = now
        base = copy.deepcopy(frame)
        served, _ = apply_pipeline(base, state)
        verdicts = detector.score_frame(served, now)
        for ac in served:
            total += 1
            v = verdicts.get(ac.get("hex"))
            if v and v.flagged:
                flags += 1
                for code, _ in v.reasons:
                    reason_counts[code] = reason_counts.get(code, 0) + 1
    return {"flags": flags, "total": total,
            "fp_rate": flags / total if total else float("nan"),
            "reasons": reason_counts}


# --------------------------------------------------------------------------- #
# Affichage
# --------------------------------------------------------------------------- #

def _fmt(x: float) -> str:
    return f"{x:5.3f}" if x == x else "  n/a"   # x!=x => NaN


def print_table(results: list[dict], baseline: dict) -> None:
    print()
    print("=" * 78)
    print("  Évaluation du détecteur de défense (D1 cinématique + D2 métadonnées)")
    print("  Vérité terrain hors-bande (ADR-0011) ; métriques par instance de piste")
    print("=" * 78)
    header = (f"{'Scénario':<16}{'Cibles':>7}{'Fausses':>8}{'TP':>6}{'FP':>6}"
             f"{'FN':>6}{'Précision':>11}{'Rappel':>9}{'F1':>8}")
    print(header)
    print("-" * 78)
    for r in results:
        fake = r["synthetic"] + r["spoofed"]
        print(f"{r['name']:<16}{r['served']:>7}{fake:>8}{r['tp']:>6}{r['fp']:>6}"
              f"{r['fn']:>6}{_fmt(r['precision']):>11}{_fmt(r['recall']):>9}"
              f"{_fmt(r['f1']):>8}")
    print("-" * 78)
    print(f"Base (sans attaque) : {baseline['flags']} alarmes / {baseline['total']} "
          f"instances  =>  taux de faux positifs {_fmt(baseline['fp_rate'])}")
    print("=" * 78)
    print("\nSignaux déclenchés par scénario (code : occurrences) :")
    for r in results:
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(r["reasons"].items(),
                                                           key=lambda kv: -kv[1]))
        print(f"  {r['name']:<16} {reasons or '(aucun)'}")
    if baseline["reasons"]:
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(baseline["reasons"].items(),
                                                          key=lambda kv: -kv[1]))
        print(f"  {'Base':<16} {reasons}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Évaluation du détecteur de défense")
    ap.add_argument("--frames", type=int, default=0,
                    help="nombre de trames à utiliser (0 = toutes)")
    ap.add_argument("--dt", type=float, default=1.0,
                    help="pas de temps virtuel entre trames (s)")
    args = ap.parse_args()

    frames, source = _load_frames(args.frames, args.dt)
    print(f"[harnais] {len(frames)} trames chargées — {source}")

    cfg = DetectorConfig()
    results = [eval_scenario(name, spec, frames, args.dt, cfg)
               for name, spec in SCENARIOS.items()]
    baseline = eval_baseline(frames, args.dt, cfg)
    print_table(results, baseline)


if __name__ == "__main__":
    main()
