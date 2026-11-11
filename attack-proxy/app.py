"""Proxy d'attaque ADS-B — serveur principal (FastAPI).

Rôle (ADR-0007) : s'interposer entre la source ADS-B réelle et co-atc.
co-atc interroge GET /aircraft.json via `source_type=readsb-api`.

INC-1 : pass-through pur (aucune attaque active) pour prouver l'interposition.
Les attaques se brancheront dans attacks/ aux incréments suivants.

Lancement :
    cd attack-proxy
    python -m pip install -r requirements.txt
    uvicorn app:app --host 127.0.0.1 --port 9900

Puis configurer co-atc :
    [adsb]
    source_type   = "readsb-api"
    readsb_api_url = "http://127.0.0.1:9900/aircraft.json"
"""

from __future__ import annotations

import glob
import os
import time

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

import attacks
import upstream
from state import STATE
from truth_log import TRUTH_LOG

HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Proxy d'attaque ADS-B", version="INC-1")

# Configuration amont depuis l'environnement (mode live / rejeu / passthrough).
STATE.configure_from_env()
# Journalisation de la vérité terrain par cycle (ADR-0011, INC-5).
# Désactivée sauf si PROXY_TRUTH_LOG est défini. Jamais servie à co-atc.
TRUTH_LOG.configure_from_env()

# Client HTTP réutilisé, entête poli pour OpenSky.
_client = httpx.Client(headers={"User-Agent": "adsb-testbed/0.1"})

# Cache amont pour respecter min_fetch_interval_s (OpenSky est rate-limité).
_cache: dict = {"ts": 0.0, "targets": []}


def _get_upstream_targets() -> list[dict]:
    now = time.time()
    with STATE.lock:
        min_interval = STATE.upstream.min_fetch_interval_s
        mode = STATE.upstream.mode
        upstream_cfg = STATE.upstream
    # En rejeu, on avance d'une trame à chaque requête : pas de cache.
    if mode != "replay_file" and now - _cache["ts"] < min_interval and _cache["targets"]:
        return _cache["targets"]
    targets = upstream.fetch_targets(upstream_cfg, _client)
    _cache["ts"] = now
    _cache["targets"] = targets
    return targets


@app.get("/aircraft.json")
def aircraft_json() -> JSONResponse:
    """Endpoint interrogé par co-atc (format dump1090, contrat ADR-0009)."""
    try:
        base = _get_upstream_targets()
        with STATE.lock:
            attacks_state = STATE.attacks
            # Liste des avions réels (hex + indicatif) pour le sélecteur de cible (V5).
            STATE.last_real_aircraft = sorted(
                ({"hex": t.get("hex"), "flight": (t.get("flight") or "").strip()}
                 for t in base if t.get("hex")),
                key=lambda a: a["flight"] or a["hex"])
        served, truth = attacks.apply_pipeline(base, attacks_state)
        with STATE.lock:
            STATE.last_served_count = len(served)
            STATE.last_truth = truth           # hors-bande (ADR-0011)
            STATE.last_error = ""
            reveal = STATE.reveal
        # Mode révélation (optionnel) : marque les leurres d'un "->" sur l'indicatif
        # pour les repérer DANS co-atc. Désactivé par défaut (attaque réaliste).
        if reveal:
            syn = truth.get("synthetic", {})
            for t in served:
                if t.get("hex") in syn:
                    fl = str(t.get("flight") or "").strip()
                    if not fl.startswith("->"):
                        t["flight"] = "->" + (fl or t.get("hex", ""))
        # Vérité terrain journalisée par cycle (hors-bande, best-effort).
        # No-op si PROXY_TRUTH_LOG n'est pas défini.
        TRUTH_LOG.log_cycle(truth)
    except Exception as exc:  # on sert une enveloppe vide plutôt que de casser co-atc
        with STATE.lock:
            STATE.last_error = str(exc)
            served = []
    return JSONResponse({
        "now": time.time(),
        "messages": len(served),
        "aircraft": served,
    })


@app.get("/api/state")
def api_state() -> dict:
    """État courant + métadonnées des attaques (pour l'UI de pilotage)."""
    snap = STATE.snapshot()
    snap["attacks_info"] = attacks.ATTACK_INFO
    snap["replays"] = _list_replays()
    snap["truth_log"] = TRUTH_LOG.status()   # état de la journalisation (ADR-0011)
    return snap


@app.post("/api/attack/{key}/params")
def api_params(key: str, payload: dict) -> dict:
    """Met à jour les paramètres d'une attaque (ex. {"trajectory_mode":"parallel"}).

    Déclarée avant la route {value} pour que « params » ne soit pas pris pour une valeur.
    """
    STATE.set_attack_params(key, payload or {})
    return api_state()


@app.post("/api/attack/{key}/{value}")
def api_toggle(key: str, value: str) -> dict:
    """Active/désactive une attaque. value ∈ {on, off}."""
    STATE.set_attack_enabled(key, value == "on")
    return api_state()


@app.post("/api/reveal/{value}")
def api_reveal(value: str) -> dict:
    """Active/désactive le marquage "->" des leurres dans co-atc. value ∈ {on, off}."""
    STATE.set_reveal(value == "on")
    return api_state()


@app.get("/api/truth")
def api_truth() -> dict:
    """Vérité terrain hors-bande : quels leurres, copies de quels avions réels.

    Réservé à l'analyste / à l'évaluation de la défense. co-atc ne lit jamais ceci.
    """
    with STATE.lock:
        return dict(STATE.last_truth)


def _list_replays() -> list[str]:
    """Fichiers de rejeu disponibles (data/*.json), chemins relatifs."""
    files = sorted(glob.glob(os.path.join(HERE, "data", "*.json")))
    return [os.path.relpath(f, HERE) for f in files]


@app.post("/api/source")
def api_source(payload: dict) -> dict:
    """Change la source amont : {"mode": "...", "replay_file": "..."}."""
    mode = payload.get("mode", "opensky")
    replay_file = payload.get("replay_file")
    STATE.set_source(mode, replay_file)
    _cache["ts"] = 0.0          # invalide le cache live
    _cache["targets"] = []
    return api_state()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Interface web de pilotage (source + attaques)."""
    with open(os.path.join(HERE, "web", "index.html"), encoding="utf-8") as fh:
        return fh.read()
