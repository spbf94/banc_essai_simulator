"""Fetcher amont : récupère le trafic « légitime » à relayer.

Deux modes (ADR-0007) :
  - "opensky"         : interroge OpenSky (anonyme) sur une zone autour de la station.
  - "passthrough_url" : relaie un aircraft.json existant (tar1090/readsb/dump1090).

Sortie commune : une liste de cibles au format du contrat ADR-0009
(dictionnaires aux noms de champs exacts attendus par co-atc).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

# --- état du rejeu (mode replay_file) ---
# Chargé une fois par chemin ; on avance d'une trame à chaque requête, en boucle.
_replay: dict = {"path": None, "frames": [], "idx": 0}

# --- cache du jeton OAuth2 OpenSky (partagé avec le compte de co-atc) ---
_token: dict = {"value": "", "expiry": 0.0}


def _opensky_token(upstream, client: httpx.Client) -> str:
    """Renvoie un jeton d'accès OpenSky (client_credentials), mis en cache.

    Lit le MÊME fichier d'identifiants que co-atc (clientId/clientSecret).
    Ne journalise jamais le secret ni le jeton.
    """
    now = time.time()
    if _token["value"] and now < _token["expiry"] - 60:
        return _token["value"]

    path = upstream.opensky_creds_path
    if not os.path.isabs(path):
        # relatif au dossier du proxy (attack-proxy/)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    with open(path) as fh:
        creds = json.load(fh)
    client_id = str(creds.get("clientId", "")).strip()
    client_secret = str(creds.get("clientSecret", "")).strip()
    if not client_id or not client_secret:
        raise ValueError(
            f"identifiants OpenSky incomplets dans {path} (clientId/clientSecret)"
        )

    resp = client.post(
        upstream.opensky_token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"échec jeton OpenSky OAuth2 : HTTP {resp.status_code}")
    data = resp.json()
    token = str(data.get("access_token", "")).strip()
    if not token:
        raise RuntimeError("réponse OAuth2 OpenSky sans access_token")
    expires_in = data.get("expires_in") or 1800
    _token["value"] = token
    _token["expiry"] = now + float(expires_in)
    return token

# --- conversions d'unités (miroir de internal/adsb/client.go) ---
M_TO_FT = 3.28084
MS_TO_KT = 1.94384
MS_TO_FTMIN = 196.8503937
NM_TO_DEG_LAT = 1.0 / 60.0  # 1 NM ≈ 1/60 degré de latitude


def _bbox(lat: float, lon: float, radius_nm: float) -> tuple[float, float, float, float]:
    """Boîte englobante (lamin, lomin, lamax, lomax) autour de la station."""
    dlat = radius_nm * NM_TO_DEG_LAT
    # correction longitude par la latitude
    import math
    dlon = dlat / max(math.cos(math.radians(lat)), 0.1)
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def fetch_opensky(upstream, client: httpx.Client) -> list[dict[str, Any]]:
    """Récupère les états OpenSky et les convertit au contrat aircraft.json.

    S'authentifie en OAuth2 (même compte que co-atc) si opensky_auth_mode=oauth2,
    ce qui lève les limites de débit de l'accès anonyme (429).
    """
    lamin, lomin, lamax, lomax = _bbox(
        upstream.station_lat, upstream.station_lon, upstream.radius_nm
    )
    url = "https://opensky-network.org/api/states/all"
    params = {"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax}
    headers = {}
    if str(upstream.opensky_auth_mode).strip().lower() == "oauth2":
        headers["Authorization"] = "Bearer " + _opensky_token(upstream, client)
    resp = client.get(url, params=params, headers=headers, timeout=15.0)
    resp.raise_for_status()
    payload = resp.json()
    now = time.time()
    targets: list[dict[str, Any]] = []
    for st in payload.get("states") or []:
        hex_ = (st[0] or "").strip().lower()
        if not hex_:
            continue
        t: dict[str, Any] = {"hex": hex_}
        callsign = (st[1] or "").strip()
        if callsign:
            t["flight"] = callsign
        if st[6] is not None:
            t["lat"] = st[6]
        if st[5] is not None:
            t["lon"] = st[5]
        if st[7] is not None:              # baro_altitude (m) -> ft
            t["alt_baro"] = round(st[7] * M_TO_FT)
        if st[9] is not None:              # velocity (m/s) -> kt
            t["gs"] = round(st[9] * MS_TO_KT, 1)
        if st[10] is not None:             # true_track (deg)
            t["track"] = st[10]
        if st[11] is not None:             # vertical_rate (m/s) -> ft/min
            t["baro_rate"] = round(st[11] * MS_TO_FTMIN)
        if st[13] is not None:             # geo_altitude (m) -> ft
            t["alt_geom"] = round(st[13] * M_TO_FT)
        if len(st) > 14 and st[14]:        # squawk
            t["squawk"] = str(st[14]).strip()
        last_contact = st[4] if st[4] is not None else now
        t["seen"] = max(0.0, round(now - float(last_contact), 1))
        t["messages"] = 1
        t["rssi"] = -20.0
        targets.append(t)
    return targets


def fetch_passthrough(url: str, client: httpx.Client) -> list[dict[str, Any]]:
    """Relaie les cibles d'un aircraft.json existant, sans les modifier."""
    resp = client.get(url, timeout=15.0)
    resp.raise_for_status()
    payload = resp.json()
    return list(payload.get("aircraft") or [])


def fetch_replay(path: str) -> list[dict[str, Any]]:
    """Rejoue un fichier de trames historiques (hors-ligne, ADR-0010).

    Sert une trame par appel, en boucle. Les cibles sont marquées « fraîches »
    (seen=0) pour ne pas être considérées comme signal perdu par co-atc.
    """
    global _replay
    if _replay["path"] != path or not _replay["frames"]:
        with open(path) as fh:
            payload = json.load(fh)
        frames = payload.get("frames") or []
        if not frames:
            raise ValueError(f"fichier de rejeu vide ou invalide : {path}")
        _replay = {"path": path, "frames": frames, "idx": 0}

    frame = _replay["frames"][_replay["idx"]]
    _replay["idx"] = (_replay["idx"] + 1) % len(_replay["frames"])

    targets = []
    for t in frame.get("aircraft") or []:
        t = dict(t)
        t["seen"] = 0
        targets.append(t)
    return targets


def fetch_targets(upstream, client: httpx.Client) -> list[dict[str, Any]]:
    """Point d'entrée : renvoie la liste de cibles selon le mode configuré."""
    if upstream.mode == "replay_file":
        if not upstream.replay_file:
            raise ValueError("mode replay_file mais aucun fichier configuré")
        return fetch_replay(upstream.replay_file)
    if upstream.mode == "passthrough_url":
        if not upstream.passthrough_url:
            raise ValueError("mode passthrough_url mais aucune URL configurée")
        return fetch_passthrough(upstream.passthrough_url, client)
    # défaut : OpenSky (live, authentifié)
    return fetch_opensky(upstream, client)
