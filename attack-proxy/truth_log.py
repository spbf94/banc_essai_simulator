"""Journalisation de la vérité terrain par cycle (ADR-0011, INC-5).

À chaque service de /aircraft.json, le proxy peut écrire en append une ligne
JSONL décrivant la vérité terrain du cycle : avions réels, leurres (avec
`clone_of`) et avions réels falsifiés (position / squawk). Cela permet, en
INC-5, de corréler *a posteriori* les verdicts du détecteur de défense avec ce
qui était réellement faux (précision / rappel).

**Hors-bande (ADR-0011).** Ce fichier n'est JAMAIS servi à co-atc ; c'est un
artefact d'analyse local. La journalisation est **désactivée par défaut** : elle
n'a lieu que si la variable d'environnement PROXY_TRUTH_LOG est définie.

    PROXY_TRUTH_LOG non défini          -> désactivé (aucun fichier écrit)
    PROXY_TRUTH_LOG=1 (ou true/on/yes)  -> actif, fichier par défaut ground_truth.jsonl
    PROXY_TRUTH_LOG=0 (ou false/off/no) -> désactivé
    PROXY_TRUTH_LOG=/chemin/fichier     -> actif, écrit dans ce fichier

Un chemin relatif est résolu par rapport au dossier attack-proxy, pour que la
sortie reste déterministe quel que soit le répertoire de lancement.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_FILENAME = "ground_truth.jsonl"
_TOGGLE_ON = {"1", "true", "on", "yes"}
_TOGGLE_OFF = {"0", "false", "off", "no", ""}


class TruthLogger:
    """Écrivain JSONL thread-safe de la vérité terrain (append, hors-bande)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.enabled = False
        self.path = ""

    def configure_from_env(self) -> None:
        """Lit PROXY_TRUTH_LOG et arme (ou non) la journalisation."""
        raw = os.environ.get("PROXY_TRUTH_LOG")
        if raw is None:
            self.enabled = False
            self.path = ""
            return
        value = raw.strip()
        low = value.lower()
        if low in _TOGGLE_OFF:
            self.enabled = False
            self.path = ""
            return
        target = DEFAULT_FILENAME if low in _TOGGLE_ON else value
        if not os.path.isabs(target):
            target = os.path.join(HERE, target)
        self.path = target
        self.enabled = True

    def status(self) -> dict:
        """Résumé pour l'UI / le debug (jamais servi à co-atc)."""
        return {"enabled": self.enabled, "path": self.path}

    def log_cycle(self, truth: dict) -> None:
        """Ajoute une ligne JSONL pour le cycle courant (no-op si désactivé).

        `truth` est la structure produite par attacks.apply_pipeline :
        clés `real_hexes`, `synthetic` (leurres: clone + ghost) et `spoofed`.
        Un échec d'écriture est avalé : il ne doit jamais casser le service à co-atc.
        """
        if not self.enabled:
            return
        synthetic = truth.get("synthetic", {}) or {}
        spoofed = truth.get("spoofed", {}) or {}
        record = {
            # Horodatage : ISO-8601 UTC lisible + epoch pour la corrélation machine.
            "ts": datetime.now(timezone.utc).isoformat(),
            "epoch": round(time.time(), 3),
            # Avions RÉELS présents ce cycle (hex de la source amont).
            "real_hex": sorted(h for h in (truth.get("real_hexes") or []) if h),
            "real_count": truth.get("real_count", 0),
            # LEURRES injectés (clones V1 + fantômes V4), avec l'original copié.
            "decoys": [
                {"hex": hx, "clone_of": meta.get("clone_of"),
                 "attack": meta.get("attack"), "kind": meta.get("kind")}
                for hx, meta in synthetic.items()
            ],
            # Avions réels FALSIFIÉS (position V2 / squawk V3).
            "spoofed": [
                {"hex": hx, "attack": meta.get("attack"),
                 "kind": meta.get("kind"), "code": meta.get("code")}
                for hx, meta in spoofed.items()
            ],
            "served_count": truth.get("served_count", 0),
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                # Journalisation best-effort : on ne compromet pas le flux co-atc.
                pass


# Instance unique du processus.
TRUTH_LOG = TruthLogger()
