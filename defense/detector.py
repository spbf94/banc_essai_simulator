"""Détecteur de plausibilité ADS-B (ADR-0006).

Le détecteur reçoit, cycle après cycle, le lot de pistes servi à co-atc (le même
`aircraft.json` que l'opérateur voit) et attribue à chaque piste un **score de
suspicion** dans [0, 1] assorti de **raisons** explicites. Il ne reçoit JAMAIS la
vérité terrain : il ne sait pas quelles cibles sont fausses. Un seuil
(`flag_threshold`) convertit le score en verdict binaire « suspecte ».

Deux familles de contrôles, conformes à l'ADR-0006 :

D1 — Plausibilité cinématique (bornes physiques + cohérence temporelle par hex)
  - Bornes de vitesse / altitude / taux de montée.
  - Accélération entre deux cycles (bornée).
  - « Téléportation » : saut de position incompatible avec la vitesse maximale
    d'un aéronef entre deux cycles (état cinématique mémorisé par `hex`).
  - Cohérence cap/vecteur : le déplacement observé entre deux cycles doit
    correspondre au couple (gs, track) annoncé. Un écart de vitesse ou de cap
    trahit une position falsifiée (V2).

D2 — Cohérence des métadonnées (analyse intra-trame + mémoire)
  - Même indicatif (`flight`) porté par plusieurs `hex` distincts et à des
    positions incompatibles → clonage (V1).
  - Squawk d'urgence (7500/7600/7700), surtout un basculement soudain vers un
    code d'urgence (V3).
  - Champs « uniformes/incohérents » : cohorte anormale de pistes partageant une
    valeur identique au bit près (altitude, RSSI…), signature d'une injection en
    masse (V4). Généralise le contrôle `NIC/NAC/SIL/RSSI uniformes` de l'ADR-0006.

Aucune dépendance à co-atc ni à attack-proxy.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# Géométrie
# --------------------------------------------------------------------------- #

_EARTH_NM = 3440.065  # rayon terrestre moyen en milles nautiques


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance grand-cercle en milles nautiques."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return 2 * _EARTH_NM * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Cap initial (degrés, 0 = Nord) du segment (1) -> (2)."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(rlat2)
    x = (math.cos(rlat1) * math.sin(rlat2)
         - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon))
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    """Écart angulaire minimal (0..180) entre deux caps."""
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def _dead_reckon(lat: float, lon: float, track: float, gs_kt: float,
                 dt_s: float) -> tuple:
    """Projette une position à vitesse (gs, track) constante pendant dt_s secondes."""
    dist_nm = gs_kt / 3600.0 * dt_s
    dlat = dist_nm / 60.0 * math.cos(math.radians(track))
    dlon = (dist_nm / 60.0 * math.sin(math.radians(track))) \
        / max(math.cos(math.radians(lat)), 0.1)
    return lat + dlat, lon + dlon


# --------------------------------------------------------------------------- #
# Seuils (documentés dans README.md). Tous ajustables à la construction.
# --------------------------------------------------------------------------- #

@dataclass
class DetectorConfig:
    # --- D1 : bornes physiques ---
    gs_max_kt: float = 650.0            # vitesse sol max plausible (aviation civile)
    alt_max_ft: float = 60000.0         # plafond plausible
    alt_min_ft: float = -1500.0         # vallée de la Mort ≈ -280 ft ; marge large
    baro_rate_max_fpm: float = 6000.0   # taux de montée/descente max plausible
    accel_max_kt_s: float = 12.0        # accélération max entre deux cycles
    # Les positions ADS-B rejouées sont quantifiées (~0.13 nm) et non monotones :
    # la vitesse instantanée d'un cycle à l'autre est du bruit. On mesure donc le
    # vecteur sur une FENÊTRE glissante, assez longue pour que la quantification
    # devienne négligeable devant la distance parcourue.
    window_min_s: float = 12.0         # ancre : échantillon le plus ancien...
    window_max_s: float = 30.0         # ...dans [min, max] s ; au-delà = coasting
    quant_nm: float = 0.35             # borne d'erreur de quantification des
                                        # positions ADS-B (élargit la tolérance aux
                                        # fenêtres courtes : marge = quant_nm/dt*3600)
    # --- D1 : téléportation / cohérence vecteur ---
    teleport_factor: float = 1.6        # saut > gs_max * facteur => téléportation
    teleport_abs_kt: float = 900.0      # vitesse implicite absolue = téléportation
    vector_speed_tol_kt: float = 60.0   # écart de base vitesse implicite vs gs
    vector_bearing_tol_deg: float = 30.0  # écart cap implicite vs track annoncé
    vector_min_speed_kt: float = 80.0   # en-deçà, bruit au sol : on ignore le cap
    # Résidu de navigation à l'estime : écart entre la position observée et celle
    # prédite depuis l'ancre à (gs, track) constants. La quantification n'y ajoute
    # qu'un terme ~constant (quant_nm), alors qu'une dérive cumulative (V2) y croît
    # avec la fenêtre — d'où un seuil = base + pente*dt.
    residual_base_nm: float = 0.6       # tolérance incompressible (quantif. + virages doux)
    residual_per_s_nm: float = 0.012    # pente : au-delà, divergence systématique
    # --- D2 ---
    dup_callsign_min_sep_nm: float = 0.5  # même flight/hex distincts séparés de +
    emergency_squawks: tuple = ("7500", "7600", "7700")
    uniform_cohort_min: int = 8         # N pistes à valeur identique => injection
    # --- fusion / seuil ---
    flag_threshold: float = 0.5
    # Poids des signaux (un signal « fort » >= seuil déclenche à lui seul).
    w_strong: float = 1.0
    w_weak: float = 0.4


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #

@dataclass
class TrackVerdict:
    hex: str
    score: float = 0.0
    reasons: list = field(default_factory=list)   # liste de (code, détail)

    @property
    def flagged(self) -> bool:
        return self._flagged

    _flagged: bool = False

    def as_dict(self) -> dict:
        return {"hex": self.hex, "score": round(self.score, 3),
                "flagged": self._flagged,
                "reasons": [r[0] for r in self.reasons]}


# --------------------------------------------------------------------------- #
# État cinématique mémorisé par hex
# --------------------------------------------------------------------------- #

@dataclass
class _Sample:
    now: float
    lat: float
    lon: float
    gs: Optional[float]
    track: Optional[float]


@dataclass
class _TrackState:
    """Historique court par hex : positions (fenêtre glissante) + dernier squawk."""
    history: list = field(default_factory=list)   # liste de _Sample, ordre ancien->récent
    last_squawk: Optional[str] = None
    last_now: float = 0.0

    def anchor(self, now: float, wmin: float, wmax: float) -> Optional[_Sample]:
        """Échantillon le plus ancien dont l'âge est dans [wmin, wmax]."""
        best = None
        for s in self.history:            # historique trié du plus ancien au récent
            age = now - s.now
            if wmin <= age <= wmax:
                return s                  # le premier (= le plus ancien) convient
            if age < wmin:
                break
        return best


# --------------------------------------------------------------------------- #
# Détecteur
# --------------------------------------------------------------------------- #

class Detector:
    """Détecteur stateful. Appeler `score_frame` une fois par cycle de données."""

    def __init__(self, config: Optional[DetectorConfig] = None) -> None:
        self.cfg = config or DetectorConfig()
        self._state: dict[str, _TrackState] = {}

    # -- API principale ---------------------------------------------------- #

    def score_frame(self, aircraft: list[dict[str, Any]],
                    now: float) -> dict[str, TrackVerdict]:
        """Note chaque piste de la trame. Renvoie {hex: TrackVerdict}.

        `aircraft` : liste de dicts au format aircraft.json (hex, lat, lon, gs,
        track, alt_baro, baro_rate, squawk, flight, rssi…).
        `now` : horodatage (s) de la trame, pour les calculs temporels par hex.
        """
        cfg = self.cfg
        verdicts: dict[str, TrackVerdict] = {}

        # ---- Pré-calcul intra-trame (D2) ---------------------------------- #
        callsign_groups = self._duplicate_callsign_groups(aircraft)
        uniform_hexes = self._uniform_cohorts(aircraft)

        for ac in aircraft:
            hx = ac.get("hex")
            if hx is None:
                continue
            v = TrackVerdict(hex=hx)

            self._check_bounds(ac, v)            # D1 bornes
            self._check_temporal(ac, now, v)     # D1 accel / téléport / vecteur
            self._check_metadata(ac, v, callsign_groups, uniform_hexes)  # D2

            v.score = min(1.0, v.score)
            v._flagged = v.score >= cfg.flag_threshold
            verdicts[hx] = v

        # ---- Mise à jour de l'état (après notation) ----------------------- #
        self._update_state(aircraft, now)
        return verdicts

    # -- D1 : bornes physiques --------------------------------------------- #

    def _check_bounds(self, ac: dict, v: TrackVerdict) -> None:
        cfg = self.cfg
        gs = _num(ac.get("gs"))
        if gs is not None and gs > cfg.gs_max_kt:
            self._add(v, cfg.w_strong, "D1_SPEED",
                      f"gs={gs:.0f}kt > {cfg.gs_max_kt:.0f}")
        alt = _num(ac.get("alt_baro"))
        if alt is not None and (alt > cfg.alt_max_ft or alt < cfg.alt_min_ft):
            self._add(v, cfg.w_strong, "D1_ALT", f"alt_baro={alt:.0f}ft hors bornes")
        rate = _num(ac.get("baro_rate"))
        if rate is not None and abs(rate) > cfg.baro_rate_max_fpm:
            self._add(v, cfg.w_strong, "D1_VRATE",
                      f"baro_rate={rate:.0f}fpm > {cfg.baro_rate_max_fpm:.0f}")

    # -- D1 : cohérence temporelle (par hex) ------------------------------- #

    def _check_temporal(self, ac: dict, now: float, v: TrackVerdict) -> None:
        cfg = self.cfg
        hx = ac.get("hex")
        st = self._state.get(hx)
        if st is None:
            return

        lat, lon = _num(ac.get("lat")), _num(ac.get("lon"))
        gs = _num(ac.get("gs"))
        if lat is None or lon is None:
            return

        # Ancre : échantillon dans la fenêtre [window_min_s, window_max_s]. On
        # mesure le vecteur sur cette base longue pour lisser la quantification
        # des positions ADS-B (±0.13 nm) qui rend la vitesse d'un cycle inexploitable.
        anc = st.anchor(now, cfg.window_min_s, cfg.window_max_s)
        if anc is None:
            return
        dt = now - anc.now
        if dt <= 0:
            return

        dist_nm = haversine_nm(anc.lat, anc.lon, lat, lon)
        implied_kt = dist_nm / dt * 3600.0
        reported_gs = gs if gs is not None else anc.gs

        # Téléportation : déplacement incompatible avec la vitesse max d'un aéronef.
        if implied_kt > max(cfg.teleport_abs_kt, cfg.gs_max_kt * cfg.teleport_factor):
            self._add(v, cfg.w_strong, "D1_TELEPORT",
                      f"{dist_nm:.1f}nm en {dt:.0f}s => {implied_kt:.0f}kt")
            return

        # Accélération sur la fenêtre (bornée). gs est souvent figé dans le rejeu,
        # donc ce contrôle ne se déclenche que sur une variation vraiment aberrante.
        if gs is not None and anc.gs is not None:
            accel = abs(gs - anc.gs) / dt
            if accel > cfg.accel_max_kt_s:
                self._add(v, cfg.w_strong, "D1_ACCEL",
                          f"Δgs/dt={accel:.1f}kt/s > {cfg.accel_max_kt_s:.0f}")

        # Cohérence cap/vecteur : le déplacement observé doit matcher (gs, track).
        # Tolérance élargie aux fenêtres courtes par la quantification des positions.
        speed_tol = cfg.vector_speed_tol_kt + cfg.quant_nm / dt * 3600.0
        if reported_gs is not None and reported_gs >= cfg.vector_min_speed_kt:
            if abs(implied_kt - reported_gs) > speed_tol:
                self._add(v, cfg.w_strong, "D1_VECTOR_SPEED",
                          f"vitesse implicite {implied_kt:.0f}kt vs gs "
                          f"{reported_gs:.0f}kt (fenêtre {dt:.0f}s)")
            track = _num(ac.get("track"))
            # Cap fiable seulement si l'aéronef a bougé d'une distance >> quantification.
            if track is not None and dist_nm > 0.3:
                obs_brg = initial_bearing_deg(anc.lat, anc.lon, lat, lon)
                if angle_diff_deg(obs_brg, track) > cfg.vector_bearing_tol_deg:
                    self._add(v, cfg.w_weak, "D1_VECTOR_HEADING",
                              f"cap observé {obs_brg:.0f}° vs track {track:.0f}°")

        # Résidu de navigation à l'estime : position observée vs prédite depuis
        # l'ancre à (gs, track) constants. Capte une dérive cumulative (V2) quelle
        # que soit sa direction, là où le contrôle de vitesse seul la manque.
        if (anc.gs is not None and anc.track is not None
                and anc.gs >= cfg.vector_min_speed_kt):
            plat, plon = _dead_reckon(anc.lat, anc.lon, anc.track, anc.gs, dt)
            residual = haversine_nm(lat, lon, plat, plon)
            tol = cfg.residual_base_nm + cfg.residual_per_s_nm * dt
            if residual > tol:
                self._add(v, cfg.w_strong, "D1_DR_RESIDUAL",
                          f"écart {residual:.1f}nm vs trajectoire prédite "
                          f"(fenêtre {dt:.0f}s)")

    # -- D2 : métadonnées -------------------------------------------------- #

    def _check_metadata(self, ac: dict, v: TrackVerdict,
                        callsign_groups: dict, uniform_hexes: dict) -> None:
        cfg = self.cfg
        hx = ac.get("hex")

        # Indicatif dupliqué sur des hex distincts (clonage V1).
        flight = _norm_flight(ac.get("flight"))
        if flight and hx in callsign_groups.get(flight, set()):
            self._add(v, cfg.w_strong, "D2_DUP_CALLSIGN",
                      f"indicatif '{flight}' porté par plusieurs hex distincts")

        # Squawk d'urgence (V3). Un basculement soudain renforce le signal.
        sq = _norm_squawk(ac.get("squawk"))
        if sq in cfg.emergency_squawks:
            st = self._state.get(hx)
            changed = st is not None and st.last_squawk != sq
            detail = f"squawk d'urgence {sq}" + (" (apparu soudainement)" if changed else "")
            self._add(v, cfg.w_strong, "D2_EMERGENCY_SQUAWK", detail)

        # Champ uniforme sur une cohorte anormale (injection en masse, V4).
        if hx in uniform_hexes:
            field_name, val, size = uniform_hexes[hx]
            self._add(v, cfg.w_strong, "D2_UNIFORM_FIELD",
                      f"{size} pistes partagent {field_name}={val}")

    # -- Agrégats intra-trame ---------------------------------------------- #

    def _duplicate_callsign_groups(self, aircraft: list[dict]) -> dict:
        """flight -> set(hex) lorsqu'un même indicatif est porté par >= 2 hex
        DISTINCTS séparés de plus de `dup_callsign_min_sep_nm`.

        On exige des hex distincts : dans les données réelles, un même avion peut
        apparaître deux fois dans une trame (même hex) — ce n'est pas un clone.
        """
        cfg = self.cfg
        by_flight: dict[str, dict] = defaultdict(dict)  # flight -> {hex: (lat,lon)}
        for ac in aircraft:
            flight = _norm_flight(ac.get("flight"))
            hx = ac.get("hex")
            if not flight or hx is None:
                continue
            lat, lon = _num(ac.get("lat")), _num(ac.get("lon"))
            by_flight[flight][hx] = (lat, lon)

        groups: dict[str, set] = {}
        for flight, hexes in by_flight.items():
            if len(hexes) < 2:
                continue
            # Au moins une paire de hex distincts séparés d'une distance notable.
            pts = [(h, ll) for h, ll in hexes.items()]
            conflict = False
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    (_, a), (_, b) = pts[i], pts[j]
                    if a[0] is None or b[0] is None:
                        conflict = True  # positions manquantes + hex distincts : suspect
                        continue
                    if haversine_nm(a[0], a[1], b[0], b[1]) >= cfg.dup_callsign_min_sep_nm:
                        conflict = True
            if conflict:
                groups[flight] = set(hexes.keys())
        return groups

    def _uniform_cohorts(self, aircraft: list[dict]) -> dict:
        """hex -> (champ, valeur, taille) pour les pistes appartenant à une
        cohorte anormalement grande partageant une valeur identique au bit près.

        Cible les champs qui devraient être ~continus/variés d'un aéronef à
        l'autre : `alt_baro` et `rssi`. Un paquet de cibles clonant exactement la
        même valeur trahit une génération automatique (flood V4, leurres uniformes).
        """
        cfg = self.cfg
        out: dict[str, tuple] = {}
        for field_name in ("alt_baro", "rssi"):
            buckets: dict[Any, set] = defaultdict(set)   # valeur -> hex DISTINCTS
            for ac in aircraft:
                val = ac.get(field_name)
                hx = ac.get("hex")
                if val is None or hx is None:
                    continue
                buckets[val].add(hx)
            for val, hexes in buckets.items():
                if len(hexes) >= cfg.uniform_cohort_min:
                    for hx in hexes:
                        # Garde la plus grande cohorte si plusieurs champs matchent.
                        prev = out.get(hx)
                        if prev is None or len(hexes) > prev[2]:
                            out[hx] = (field_name, val, len(hexes))
        return out

    # -- Divers ------------------------------------------------------------ #

    def _update_state(self, aircraft: list[dict], now: float) -> None:
        cfg = self.cfg
        for ac in aircraft:
            hx = ac.get("hex")
            if hx is None:
                continue
            st = self._state.get(hx)
            if st is None:
                st = _TrackState()
                self._state[hx] = st
            st.last_squawk = _norm_squawk(ac.get("squawk"))
            st.last_now = now
            lat, lon = _num(ac.get("lat")), _num(ac.get("lon"))
            if lat is None or lon is None:
                continue
            st.history.append(_Sample(now=now, lat=lat, lon=lon,
                                      gs=_num(ac.get("gs")),
                                      track=_num(ac.get("track"))))
            # Ne garde que la fenêtre utile (+ petite marge).
            cutoff = now - (cfg.window_max_s + 5.0)
            st.history = [s for s in st.history if s.now >= cutoff]
        # Purge des hex disparus depuis longtemps (évite une fuite mémoire).
        stale = [h for h, s in self._state.items() if now - s.last_now > 120]
        for h in stale:
            del self._state[h]

    def _add(self, v: TrackVerdict, weight: float, code: str, detail: str) -> None:
        v.score += weight
        v.reasons.append((code, detail))

    def reset(self) -> None:
        self._state.clear()


# --------------------------------------------------------------------------- #
# Helpers de normalisation
# --------------------------------------------------------------------------- #

def _num(x: Any) -> Optional[float]:
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _norm_flight(x: Any) -> str:
    return str(x).strip().upper() if x else ""


def _norm_squawk(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    return s or None
