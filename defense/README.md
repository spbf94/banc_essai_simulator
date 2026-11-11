# Détecteur de défense ADS-B (module `defense/`)

Module de **remédiation** du banc d'essai ADS-B (dépôt co-atc). Il met en œuvre
l'[ADR-0006](../docs/adr/0006-strategie-defense-plausibilite.md) : un détecteur
qui attribue à **chaque piste** un *score de suspicion* à partir de contrôles de
plausibilité, puis mesure son efficacité contre les attaques V1–V4.

- **Module séparé.** Aucune ligne de co-atc ni du proxy d'attaque n'est modifiée.
  Le détecteur consomme le flux de pistes *tel que co-atc le reçoit*
  (`aircraft.json`). Le harnais d'évaluation, lui, importe le moteur d'attaques
  du proxy uniquement pour fabriquer des données de test.
- **Sans vérité terrain.** Conformément à l'[ADR-0011](../docs/adr/0011-verite-terrain-et-evaluation.md),
  le détecteur ne voit jamais quels avions sont faux. La vérité terrain n'est
  lue qu'*a posteriori*, par le harnais, pour calculer précision et rappel.

```
defense/
  detector.py    # cœur : classe Detector (D1 cinématique + D2 métadonnées)
  evaluate.py    # harnais d'évaluation (précision/rappel par scénario V1–V4)
  __init__.py    # expose Detector, TrackVerdict
  README.md
```

## Utilisation

Évaluation (produit le tableau de résultats) :

```bash
python3 defense/evaluate.py            # toutes les trames du rejeu
python3 defense/evaluate.py --frames 200
```

Le harnais charge `attack-proxy/data/sample_replay.json` (et le **régénère** au
besoin via `attack-proxy/tools/export_replay.py` depuis `data/*.db`).

Comme bibliothèque, pour noter un flux en direct :

```python
from defense import Detector
det = Detector()
# à chaque cycle de données (liste de dicts aircraft.json + horodatage s) :
verdicts = det.score_frame(aircraft, now)
for hx, v in verdicts.items():
    if v.flagged:
        print(hx, round(v.score, 2), [code for code, _ in v.reasons])
```

## Contrôles implémentés

### D1 — Plausibilité cinématique (état mémorisé par `hex`)

| Code | Contrôle | Seuil par défaut |
|------|----------|------------------|
| `D1_SPEED` | Vitesse sol hors borne | `gs > 650 kt` |
| `D1_ALT` | Altitude hors borne | `alt_baro ∉ [-1500, 60000] ft` |
| `D1_VRATE` | Taux de montée/descente hors borne | `|baro_rate| > 6000 fpm` |
| `D1_ACCEL` | Accélération excessive (sur la fenêtre) | `|Δgs|/dt > 12 kt/s` |
| `D1_TELEPORT` | Saut de position incompatible avec la vitesse max | `> max(900 kt, 650×1.6)` |
| `D1_VECTOR_SPEED` | Vitesse implicite (déplacement) ≠ `gs` annoncée | `> 60 kt + 0.35 nm/dt` |
| `D1_VECTOR_HEADING` | Cap du déplacement ≠ `track` annoncé | `> 30°` (signal faible) |
| `D1_DR_RESIDUAL` | Écart à la trajectoire prédite par navigation à l'estime | `> 0.6 nm + 0.012 nm/s × dt` |

**Fenêtre glissante.** Les positions ADS-B rejouées sont **quantifiées**
(≈ 0,13 nm) et non monotones : la vitesse d'un cycle à l'autre est du bruit
(la position oscille de ±1 quantum). Mesurer le vecteur sur un seul cycle génère
des sauts fantômes jusqu'à ~2000 kt sur des avions parfaitement légitimes. Le
détecteur mesure donc le déplacement sur une **fenêtre de 12 à 30 s** (ancre =
échantillon le plus ancien de la fenêtre), où la quantification devient
négligeable devant la distance parcourue. La tolérance de vitesse est en outre
élargie d'un terme `quant_nm/dt` qui borne l'erreur de quantification restante.

Au-delà de 30 s sans mise à jour, la piste est considérée comme « coastée » : on
ne tire aucune conclusion cinématique (évite les faux sauts après une absence).

Le **résidu de navigation à l'estime** (`D1_DR_RESIDUAL`) est la clé contre la
dérive de trajectoire (V2) : on compare la position observée à celle prédite
depuis l'ancre à `(gs, track)` constants. La quantification n'ajoute qu'un terme
quasi constant au résidu, tandis qu'une **dérive cumulative** le fait croître
avec la fenêtre — d'où un seuil `base + pente×dt` qui les sépare, quelle que
soit la direction de la dérive.

### D2 — Cohérence des métadonnées (analyse intra-trame + mémoire)

| Code | Contrôle | Déclenchement |
|------|----------|---------------|
| `D2_DUP_CALLSIGN` | Même indicatif (`flight`) porté par **plusieurs `hex` distincts** à des positions incompatibles | ≥ 2 hex, séparés de ≥ 0.5 nm |
| `D2_EMERGENCY_SQUAWK` | Squawk d'urgence (7500/7600/7700), *a fortiori* un basculement soudain | squawk ∈ {7500,7600,7700} |
| `D2_UNIFORM_FIELD` | Cohorte anormale de pistes partageant une valeur **identique au bit près** (altitude, RSSI…) | ≥ 8 `hex` distincts à valeur égale |

Remarque sur `D2_DUP_CALLSIGN` : dans les données réelles, un même avion apparaît
parfois deux fois dans une trame (**même `hex`**, mise à jour infra-seconde) — ce
n'est pas un clone. Le contrôle exige donc des **`hex` distincts** portant le
même indicatif, ce qui est physiquement impossible (un indicatif = une adresse
ICAO = un aéronef). Le contrôle `D2_UNIFORM_FIELD` généralise la détection des
champs `NIC/NAC/SIL/RSSI` uniformes de l'ADR-0006 ; sur le jeu de données courant
les altitudes réelles sont des flottants haute précision tous distincts, si bien
que seule une **injection automatique** (flood V4, altitude figée à 30000) forme
une cohorte identique.

### Fusion et seuil

Chaque signal « fort » pèse 1.0, le signal faible (`D1_VECTOR_HEADING`) 0.4. Le
score est la somme bornée à 1.0 ; une piste est **signalée** si `score ≥ 0.5`.
Ainsi un seul signal fort suffit, et le cap seul (faible) ne déclenche jamais à
lui seul une alarme — il ne fait que corroborer. Tous les seuils sont réunis dans
`DetectorConfig` (`detector.py`) et ajustables à la construction.

## Méthode d'évaluation

1. On rejoue `sample_replay.json` trame par trame. Pour le **temps**, le harnais
   reconstitue l'horodatage réel de chaque trame depuis `data/*.db` (le JSON ne
   les porte pas) ; la cinématique a besoin du temps réellement écoulé. À défaut
   de base, il retombe sur un pas fixe.
2. Pour chaque scénario on active **une** attaque et on applique
   `attacks.apply_pipeline`, qui renvoie `(cibles_servies, vérité_terrain)`.
3. Le détecteur note les cibles servies **sans** la vérité terrain.
4. On compare les verdicts à la vérité terrain. Métriques calculées **par
   instance de piste** (chaque couple trame×piste est un échantillon), sur toutes
   les trames.

*Horloge virtuelle* : les leurres (V1/V4) et la dérive (V2) avancent par
navigation à l'estime en lisant `time.time()`. En rejeu accéléré, le harnais
remplace cette horloge par l'horodatage réel de la trame pour une cinématique
réaliste. Le moteur d'attaques et le proxy ne sont pas modifiés.

Paramètres d'attaque utilisés (documentés dans `SCENARIOS`, `evaluate.py`) :
V1 `n=3` divergent · V2 `count=3, drift_kt=150` · V3 `7700, count=3` ·
V4 `count=60`.

## Résultats

Rejeu `sample_replay.json` (371 trames, source `co-atc-2026-11-09.db`) :

| Scénario | Cibles | Fausses | TP | FP | FN | Précision | Rappel | F1 |
|----------|-------:|--------:|---:|---:|---:|----------:|-------:|---:|
| V1 clonage     | 21380 | 16035 | 14439 | 4814 | 1596 | **0.750** | **0.900** | 0.818 |
| V2 trajectoire |  5345 |  1094 |   598 |   34 |  534 | **0.946** | **0.528** | 0.678 |
| V3 squawk      |  5345 |  1094 |  1094 |    6 |   38 | **0.995** | **0.966** | 0.980 |
| V4 flood       | 27605 | 22260 | 22260 |   13 |    0 | **0.999** | **1.000** | 1.000 |

**Base (aucune attaque) : 13 alarmes / 5345 instances → taux de faux positifs 0.2 %.**

Signaux dominants : V1 → `D2_DUP_CALLSIGN` ; V2 → `D1_DR_RESIDUAL` ;
V3 → `D2_EMERGENCY_SQUAWK` ; V4 → `D2_UNIFORM_FIELD`.

### Lecture des faux positifs et des limites

- **Taux de faux positifs très bas (0,2 %)** sur trafic réel non attaqué : les 13
  alarmes résiduelles sont des `D1_VECTOR_SPEED`/`D1_DR_RESIDUAL` sur des
  manœuvres brusques légitimes (virages serrés où la corde du déplacement
  s'écarte de la route annoncée), faux positifs explicitement anticipés par
  l'ADR-0006.
- **V1 — précision 0,75 (par construction).** Quand un indicatif est porté par
  plusieurs `hex`, le détecteur signale **tout le groupe** : les 3 clones (TP)
  *et* l'avion original (FP). C'est le comportement opérationnel correct — aucune
  des pistes homonymes n'est fiable tant que le conflit n'est pas levé — mais il
  compte l'original comme faux positif (≈ 1 FP pour 3 TP, d'où 0,75).
- **V1 — rappel 0,90.** Les 10 % de clones non détectés sont les copies d'avions
  qui **n'émettent aucun indicatif** (10 % des enregistrements réels) : sans
  `flight`, le contrôle d'indicatif dupliqué ne peut pas les regrouper, et un
  clone est cinématiquement cohérent avec lui-même. Limite réelle qui motive un
  contrôle multi-récepteurs (D3/MLAT).
- **V2 — rappel 0,53.** La dérive est **cumulative et initialement sous le
  plancher de bruit** des positions ADS-B : les premières trames (faible écart
  accumulé) sont indétectables, puis la détection devient quasi certaine à mesure
  que l'écart croît. Précision élevée (0,95) : quand on signale, c'est à juste
  titre. C'est l'attaque « physiquement cohérente » dont l'ADR-0006 prévoit
  qu'elle échappe en partie à D1 seul.
- **V3 / V4 — quasi parfaits.** Squawk d'urgence et injection en masse à altitude
  figée laissent des signatures franches (métadonnées).

## Recommandation ADR-0006

Le prototype est **validé** : détecteur en module séparé, deux familles de
contrôles opérationnelles, précision/rappel mesurés sur V1–V4 avec un **taux de
faux positifs de 0,2 %** sur trafic réel. V3 et V4 sont neutralisés (F1 ≥ 0,98),
V1 détecté à 0,90 de rappel, V2 — l'attaque la plus subtile — partiellement, avec
une précision élevée. Les limites observées (clones sans indicatif, dérive sous
le bruit) sont documentées et **motivent la piste D3 (MLAT/TDOA multi-récepteurs)**
déjà évoquée, mais non bloquante pour cette itération.

➡️ **L'ADR-0006 peut passer de « Proposé » à « Accepté ».**
