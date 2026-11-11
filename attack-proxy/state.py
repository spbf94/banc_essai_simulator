"""État partagé du proxy d'attaque.

Détient la configuration amont (d'où vient le trafic) et la liste des attaques
actives. Lu à chaque cycle par le pipeline, modifié par l'UI de pilotage.

INC-1 : seul le pass-through est câblé ; la liste d'attaques reste vide
(le flux traverse sans modification). Les attaques V1-V4 s'y brancheront
aux incréments suivants.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field


@dataclass
class UpstreamConfig:
    # Mode de source amont (ADR-0010) :
    #   "opensky"         source live, zone autour de la station
    #   "replay_file"     rejeu hors-ligne d'un fichier de trames historiques
    #   "passthrough_url" relais d'un aircraft.json existant
    mode: str = "opensky"
    # Zone OpenSky (bbox) — par défaut autour de CYYZ (Toronto Pearson),
    # alignée sur la station co-atc. Ajuster si la station change.
    station_lat: float = 43.6777
    station_lon: float = -79.6248
    radius_nm: float = 50.0
    # Fichier de rejeu pour le mode replay_file
    replay_file: str = ""
    # URL source pour le mode passthrough_url
    passthrough_url: str = ""
    # Délai mini entre deux fetch amont (anti-rate-limit OpenSky ; ignoré en rejeu)
    min_fetch_interval_s: float = 5.0
    # --- Authentification OpenSky (mode opensky) ---
    # Réutilise le MÊME compte que co-atc : fichier d'identifiants partagé.
    opensky_auth_mode: str = "oauth2"           # "oauth2" ou "anonymous"
    opensky_creds_path: str = "../configs/opensky_credentials.json"
    opensky_token_url: str = (
        "https://auth.opensky-network.org/auth/realms/"
        "opensky-network/protocol/openid-connect/token"
    )


@dataclass
class AttackState:
    """Interrupteurs et paramètres des attaques (inertes à INC-1)."""
    # Activation par scénario — tous désactivés par défaut.
    enabled: dict = field(default_factory=lambda: {
        "v1_clone": False,
        "v2_trajectory": False,
        "v3_squawk": False,
        "v4_flood": False,
        "v5_targeted": False,
    })
    # Paramètres des attaques.
    params: dict = field(default_factory=lambda: {
        "v1_clone": {"n": 3, "pos_jitter_deg": 0.02, "heading_spread_deg": 90,
                     "gs_jitter": 0.25, "turn_rate_deg_s": 2.0,
                     "trajectory_mode": "divergent"},   # "divergent" | "parallel"
        "v2_trajectory": {"count": 1, "drift_kt": 150},
        "v3_squawk": {"code": "7700", "count": 1},       # 7500 | 7600 | 7700
        "v4_flood": {"count": 60, "spread_deg": 0.5},
        "v5_targeted": {"target": "", "mode": "ghost_frontal",
                        "lead_time_s": 45, "descent_fpm": 2500,
                        "turn_rate_deg_s": 3.0,
                        "airport_lat": 43.6777, "airport_lon": -79.6248},
    })


class SharedState:
    """Conteneur thread-safe partagé entre le serveur web et le pipeline."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.upstream = UpstreamConfig()
        self.attacks = AttackState()
        # Dernier instantané servi (pour l'UI / le debug).
        self.last_served_count = 0
        self.last_error = ""
        # Dernière vérité terrain (hors-bande, ADR-0011) : jamais servie à co-atc.
        self.last_truth = {"synthetic": {}, "synthetic_count": 0,
                           "real_count": 0, "served_count": 0}
        # Mode « révélation » : si activé, les leurres sont marqués d'un préfixe
        # "->" sur leur indicatif DANS le flux servi à co-atc, pour les repérer
        # à l'écran. Désactivé par défaut (attaque réaliste, rien ne les trahit).
        self.reveal = False
        # Avions réels du dernier cycle (hex + indicatif), pour alimenter le
        # sélecteur d'« avion cible » de l'attaque ciblée (V5) dans l'UI.
        self.last_real_aircraft: list = []

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "upstream": {
                    "mode": self.upstream.mode,
                    "station_lat": self.upstream.station_lat,
                    "station_lon": self.upstream.station_lon,
                    "radius_nm": self.upstream.radius_nm,
                    "passthrough_url": self.upstream.passthrough_url,
                },
                "attacks_enabled": dict(self.attacks.enabled),
                "attacks_params": {k: dict(v) for k, v in self.attacks.params.items()},
                "last_served_count": self.last_served_count,
                "last_error": self.last_error,
                "synthetic_count": self.last_truth.get("synthetic_count", 0),
                "spoofed_count": self.last_truth.get("spoofed_count", 0),
                "reveal": self.reveal,
                "aircraft": list(self.last_real_aircraft),
            }

    def configure_from_env(self) -> None:
        """Surcharge la config amont depuis les variables d'environnement.

        PROXY_UPSTREAM_MODE   opensky | replay_file | passthrough_url
        PROXY_REPLAY_FILE     chemin du fichier de rejeu (mode replay_file)
        PROXY_PASSTHROUGH_URL URL source (mode passthrough_url)
        PROXY_STATION_LAT/LON station pour la zone OpenSky
        PROXY_RADIUS_NM       rayon de la zone OpenSky
        """
        with self._lock:
            u = self.upstream
            u.mode = os.environ.get("PROXY_UPSTREAM_MODE", u.mode)
            u.replay_file = os.environ.get("PROXY_REPLAY_FILE", u.replay_file)
            u.passthrough_url = os.environ.get("PROXY_PASSTHROUGH_URL", u.passthrough_url)
            u.opensky_auth_mode = os.environ.get("PROXY_OPENSKY_AUTH_MODE", u.opensky_auth_mode)
            u.opensky_creds_path = os.environ.get("PROXY_OPENSKY_CREDS", u.opensky_creds_path)
            u.opensky_token_url = os.environ.get("PROXY_OPENSKY_TOKEN_URL", u.opensky_token_url)
            for env, attr in (("PROXY_STATION_LAT", "station_lat"),
                              ("PROXY_STATION_LON", "station_lon"),
                              ("PROXY_RADIUS_NM", "radius_nm")):
                if env in os.environ:
                    try:
                        setattr(u, attr, float(os.environ[env]))
                    except ValueError:
                        pass

    def set_attack_enabled(self, key: str, value: bool) -> None:
        with self._lock:
            if key in self.attacks.enabled:
                self.attacks.enabled[key] = bool(value)

    def set_attack_params(self, key: str, updates: dict) -> None:
        """Fusionne des paramètres dans une attaque (depuis l'UI)."""
        with self._lock:
            if key in self.attacks.params and isinstance(updates, dict):
                self.attacks.params[key].update(updates)

    def set_reveal(self, value: bool) -> None:
        """Active/désactive le marquage "->" des leurres dans le flux servi."""
        with self._lock:
            self.reveal = bool(value)

    def set_source(self, mode: str, replay_file: str | None = None) -> None:
        """Change la source amont à chaud (depuis l'UI)."""
        with self._lock:
            if mode in ("opensky", "replay_file", "passthrough_url"):
                self.upstream.mode = mode
            if replay_file is not None:
                self.upstream.replay_file = replay_file

    @property
    def lock(self) -> threading.RLock:
        return self._lock


# Instance unique du processus.
STATE = SharedState()
