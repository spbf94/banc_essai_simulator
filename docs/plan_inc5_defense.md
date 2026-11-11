# Plan d'implémentation INC-5 — Détecteur de défense D1/D2

Plan d'architecture (pas de code) pour l'incrément **INC-5** de la feuille de route
([roadmap](roadmap.md)). Agent pilote : `adsb-dev-defense`.
Décisions de référence : [ADR-0006](adr/0006-strategie-defense-plausibilite.md) (stratégie D1/D2),
[ADR-0009](adr/0009-contrat-aircraft-json.md) (contrat du flux),
[ADR-0011](adr/0011-verite-terrain-et-evaluation.md) (vérité terrain hors-bande).

- **Date :** 2026-11-09
- **Pré-requis :** ADR-0006 (`Proposé`) → passe à `Accepté` en fin d'incrément, une fois les seuils fixés et le prototype validé.
- **Statut INC-5 :** À faire.

---

## 1. Objet et invariants

Fournir la **remédiation démontrable** du banc : un module qui lit le même flux ADS-B
que l'opérateur co-atc, attribue à chaque piste un **score de confiance** (via les
contrôles D1 cinématique et D2 métadonnées), signale les pistes implausibles, puis se
fait **évaluer** (précision/rappel par scénario) contre la vérité terrain du proxy.

Invariants non négociables (hérités de l'architecture et des ADR) :

1. **Dossier séparé `defense/`.** Aucune ligne de co-atc ni d'`attack-proxy/` n'est modifiée
   (roadmap §« structure cible » ; porte conformité INC-5).
2. **Le détecteur ne voit jamais la vérité terrain.** Il ne consomme **que** le flux public
   `aircraft.json` (contrat ADR-0009). `GET /api/truth` est réservé au **harnais d'évaluation**,
   qui est un exécutable distinct (ADR-0011). Cette séparation est structurelle : le code du
   détecteur n'a aucune référence, même en import, à l'endpoint de vérité.
3. **Aucune émission RF, tout en localhost** (ADR-0004).
4. **Pile Python** (cohérence avec le proxy, réutilisation de la connaissance du contrat ADR-0009),
   sans dépendance au code du proxy ni de co-atc : le seul couplage est le **contrat HTTP** `aircraft.json`.

---

## 2. Où et comment le détecteur consomme les données

### 2.1 Point de prélèvement (tap)

Le détecteur **poll** l'endpoint `GET /aircraft.json` servi par le proxy
(`http://127.0.0.1:9900/aircraft.json`), c.-à-d. **exactement l'enveloppe que co-atc ingère**.
Il voit donc rigoureusement ce que voit l'opérateur : réels + leurres + positions/squawks
falsifiés, sans aucun marqueur distinctif (ADR-0011 : pas de champ `_synthetic`, hex des leurres
plausibles). C'est la condition d'une évaluation honnête.

```
                         GET /aircraft.json (contrat ADR-0009)
  attack-proxy :9900  ─────────────┬───────────────▶  co-atc  (source_type=readsb-api)
   (moteur d'attaques)             │
                                   └───────────────▶  defense/ (détecteur)   ← ce plan
                                   (même flux, sans la vérité terrain)

  GET /api/truth  ────────────────────────────────▶  defense/evaluate (harnais)  ← hors-bande
```

**Pourquoi le proxy et pas l'API de co-atc ?** Prélever au niveau de `aircraft.json` garantit
que le détecteur et l'opérateur partagent **la même entrée brute**, isole le détecteur de toute
transformation interne de co-atc, et n'exige aucune modification de co-atc. (Variante « lire
l'API `/api/v1` de co-atc » : écartée car elle introduit un couplage et masque/renomme des champs ;
**décision à acter en ADR-0013**, voir §10.)

### 2.2 Besoin d'un état inter-cycles

Une seule trame ne porte pas les dérivées nécessaires à D1 (le saut de position, l'accélération,
la cohérence cap/déplacement se mesurent **entre** deux trames). Le détecteur maintient donc un
**historique glissant par `hex`** : positions, `gs`, `track`, `alt_baro`, `baro_rate`, `squawk`,
horodatage `now` de l'enveloppe. Fenêtre courte (p. ex. 30–60 s ou N=10 dernières trames),
purge des pistes muettes (cohérent avec `signal_lost_timeout_seconds` du proxy).

### 2.3 Cadence

Le poller interroge à une cadence configurable (`poll_interval_s`, défaut 2–5 s). En **mode rejeu**,
le proxy avance d'une trame par requête (`upstream.py:fetch_replay`) : le détecteur et le harnais
d'évaluation doivent donc interroger **au même rythme** pour rester alignés sur la même trame
(voir §6.2, synchronisation).

---

## 3. D1 — Plausibilité cinématique

Objectif : repérer les pistes dont le mouvement viole la physique de vol ou l'auto-cohérence du
message. Chaque contrôle produit un **sous-score** [0,1] (0 = plausible, 1 = violation franche)
et une étiquette lisible (pour la démo et le rapport). Réutilise les unités et formules du proxy
(`upstream.py`) et l'esprit de `internal/physics/physics.go` (conversions, `SignedAngleDiffDeg`,
`FlightPathAngleDeg`).

| Réf | Contrôle | Principe | Seuil (défaut, à régler) | Cible principale |
|-----|----------|----------|--------------------------|------------------|
| D1-a | **Saut de position** | Vitesse implicite entre deux trames `v_impl = dist(p_t, p_{t-1}) / dt` comparée à `gs` déclaré et à un plafond absolu | `v_impl > max(1.5·gs, gs+150 kt)` ou `v_impl > 1200 kt` | **V2** (dérive 150 kt cumulée), téléportations |
| D1-b | **Cohérence cap/déplacement** | Angle entre le `track` déclaré et le **relèvement** du déplacement réel observé | `|Δ| > 25–40°` soutenu sur ≥2 trames | **V2** (le déplacement suit le cap de dérive, pas `track`) |
| D1-c | **Accélération** | `|Δgs| / dt` hors enveloppe avion | `> 10 kt/s` (≈ 0,5 g) | Sauts de vitesse artificiels |
| D1-d | **Taux vertical / pente** | `baro_rate` et pente `FlightPathAngleDeg(baro_rate, gs)` hors bornes ; cohérence `Δalt/dt` vs `baro_rate` | `|baro_rate| > 6000 ft/min` ou pente > 30° | Altitudes incohérentes |
| D1-e | **Bornes d'enveloppe** | `gs`, `alt_baro` hors domaine plausible (ex. `gs<0`, `gs>700 kt` sous FL300, alt négative) | bornes par catégorie | Cibles grossières |
| D1-f | **Continuité temporelle** | Apparition/disparition anormalement fréquente d'un même `hex` au même instant | — | Appui pour V4 |

**Portée par attaque :**
- **V2** est la cible de choix de D1 (D1-a + D1-b) : la position réelle dérive de `drift_kt`
  (défaut 150 kt) **en plus** du mouvement réel, donc la vitesse implicite et le relèvement
  trahissent la manipulation, alors que `gs`/`track` déclarés restent « normaux ».
- **V1 échappe largement à D1** : chaque leurre a une cinématique **propre et plausible**
  (navigation à l'estime, `v1_clone.py`). C'est voulu (ADR-0006, conséquences) et c'est le rôle de D2.
- **V4** : chaque fantôme est individuellement plausible (cinématique propre, `v4_flood.py`) ;
  D1 ne le prend que marginalement (D1-f). D2 et le contrôle de **recensement** (§4) font le travail.
- **V3** : D1 ne s'applique pas (un vrai 7700 bouge normalement) — voir limites §9.

---

## 4. D2 — Cohérence des métadonnées

Objectif : repérer les incohérences d'identité/intégrité qu'un attaquant « physiquement cohérent »
ne peut pas masquer. Contrôles au niveau **de la trame** et **du voisinage de pistes**.

| Réf | Contrôle | Principe | Seuil (défaut) | Cible principale |
|-----|----------|----------|----------------|------------------|
| D2-a | **Indicatif dupliqué à plusieurs positions** | Même `flight` (callsign) porté par ≥2 `hex` distincts séparés de plus que l'empan plausible d'un même vol | `≥2 hex` même `flight`, distance > 2–5 NM | **V1** (leurres au même indicatif) |
| D2-b | **Grappe autour d'un original** | N pistes de même `flight`/type divergeant depuis un point commun (signature du facteur N de clonage) | `N ≥ 2` divergent | **V1** |
| D2-c | **Indicatif synthétique / métadonnées manquantes** | Motif de callsign régulier (`GH####`), absence de `type`/registration, `alt_baro` identique sur un lot | lot homogène | **V4** |
| D2-d | **Pic de recensement** | Hausse soudaine du nombre de pistes vs moyenne glissante (nouvelles pistes/seconde) | `+X σ` ou `> seuil` | **V4** |
| D2-e | **Téléportation d'adresse ICAO** | Un même `hex` saute de position incompatible avec la continuité (recoupe D1-a côté identité) | cf. D1-a | Spoofing d'adresse |
| D2-f | **Champs d'intégrité / RSSI** | `NIC/NAC/SIL` absents/uniformes, `rssi` constant ou absent sur un sous-ensemble | indicatif, **faible ici** | Appui (voir limites) |

**Portée par attaque :**
- **V1 est la cible de D2** (D2-a, D2-b) : les leurres **partagent l'indicatif** de l'original
  (`v1_clone.py` : `c = dict(t)` conserve `flight`/type). Un même callsign à plusieurs positions
  éloignées est la signature forte et explicable. C'est le cœur de la démo « D1 ne voit pas,
  D2 démasque ».
- **V4** : D2-c (callsign `GHxxxx`, `alt_baro=30000` uniforme, pas de type) + D2-d (pic de recensement).
- **V2/V3** : D2 ne les cible pas directement (ils réutilisent le vrai `hex`/`flight`).

**Note sur D2-f (limite du banc).** Le flux produit par le proxy **ne contient pas** `NIC/NAC/SIL`
(absents du contrat ADR-0009 et des sources), et le `rssi` est constant (OpenSky : `-20.0`) ou absent
(fantômes). D2-f est donc **documenté mais peu discriminant** dans ce banc ; on le garde comme contrôle
« prêt pour un flux réel » et on ne le compte pas dans les métriques principales. À signaler dans le rapport.

---

## 5. Fusion des scores et verdict

- Chaque piste reçoit un vecteur de sous-scores (D1-a…D1-f, D2-a…D2-f) + étiquettes déclenchées.
- **Score de piste** = agrégation (max pondéré ou somme bornée) des sous-scores → `confidence_penalty ∈ [0,1]`.
  On privilégie un agrégateur **explicable** (le contrôle dominant + sa raison), pas une boîte noire
  (ADR-0006 : explicabilité en démonstration).
- **Verdict binaire** par seuil `decision_threshold` (défaut 0,5) : `flagged` / `clean`.
- Sortie du détecteur : par cycle, liste `{hex, flight, flagged, penalty, reasons[]}`, journalisée
  (JSONL horodaté) et, pour la démo, un petit affichage/console. **Aucune action sur co-atc** : le
  détecteur observe et signale, il ne filtre pas le flux (séparation stricte).

Seuils et pondérations = **paramètres configurables** (§8), figés par mesure en fin d'incrément.

---

## 6. Vérité terrain et évaluation (sans la fournir au détecteur)

### 6.1 Séparation stricte

Deux programmes distincts dans `defense/` :

- **`detector` / `poller`** : lit `GET /aircraft.json` uniquement. Produit des verdicts. **Zéro accès à `/api/truth`.**
- **`evaluate` (harnais)** : lit **à la fois** `GET /aircraft.json` *et* `GET /api/truth` au même cycle,
  rejoue le détecteur sur la trame, puis compare verdicts ↔ vérité. C'est le seul composant qui connaît la vérité.

Ainsi la vérité terrain ne **conditionne jamais** une décision du détecteur ; elle ne sert qu'au
calcul *a posteriori* de précision/rappel (ADR-0011).

### 6.2 Protocole d'évaluation

1. **Étiquetage de référence** à partir de `/api/truth` (structure produite par `attacks.apply_pipeline`) :
   - `synthetic` (hex → `{attack, kind∈{clone,ghost}, clone_of}`) → pistes **positives** (fausses).
   - `spoofed` (hex → `{attack, kind∈{spoofed_pos,spoofed_squawk}, code}`) → pistes réelles **manipulées** (positives au sens « à signaler »).
   - Tout autre `hex` servi = **négatif** (réel non touché).
2. **Appariement** par `hex` entre le verdict du détecteur (`flagged`) et l'étiquette de référence, sur la même trame.
3. **Comptage** TP / FP / FN / TN par cycle, cumulés sur la fenêtre d'un scénario.
4. **Synchronisation rejeu** : interroger `/aircraft.json` puis `/api/truth` en séquence rapprochée.
   Comme le mode rejeu avance d'une trame par requête, le harnais doit soit (a) piloter lui-même un seul
   consommateur et dériver la vérité du même appel, soit (b) utiliser le mode `opensky`/`passthrough`
   (trame stable sur `min_fetch_interval_s`). **Point de vigilance à tester** (voir §11) ; recommandation :
   évaluer de préférence sur source stable, ou faire du harnais l'**unique** client du proxy pendant la mesure.

### 6.3 Pilotage reproductible des scénarios

Le harnais peut activer/désactiver chaque attaque via l'API existante du proxy
(`POST /api/attack/{key}/{on|off}`, `POST /api/attack/{key}/params`) pour dérouler V1→V4 de façon
scriptée et reproductible (démo rejouable, roadmap INC-6). Il ne fait qu'**utiliser** l'API publique du
proxy — aucune modification de celui-ci.

---

## 7. Métriques — précision/rappel par scénario

**Classe positive = « piste affectée par une attaque »** (synthétique *ou* réelle manipulée).
Pour chaque scénario, un seul vecteur d'attaque actif (plus, en option, un scénario combiné) :

| Scénario | Attaque active | Positifs attendus | Contrôle censé déclencher | Attendu |
|----------|----------------|-------------------|---------------------------|---------|
| **V1** | clonage | les leurres (`kind=clone`) | **D2-a/D2-b** | rappel élevé ; D1 ~0 (attendu) |
| **V2** | dérive de trajectoire | réels `spoofed_pos` | **D1-a/D1-b** | rappel élevé après quelques trames (dérive cumulative) |
| **V3** | faux squawk | réels `spoofed_squawk` | métadonnée squawk (hors D1/D2 strict) | **rappel faible/partiel — limite documentée** |
| **V4** | flood | fantômes (`kind=ghost`) | **D2-c/D2-d** | rappel élevé ; surveiller FP sur recensement |

Pour chaque scénario :

- **Précision** = TP / (TP + FP) ; **Rappel** = TP / (TP + FN) ; F1 en appoint.
- **Tableau avant/après défense** (roadmap, critère de sortie) : *avant* = aucun détecteur (l'opérateur
  ne distingue rien → rappel effectif 0, 100 % des faux « acceptés ») ; *après* = détecteur actif.
- **Catalogue des faux positifs** : lister les pistes réelles signalées à tort et la raison (ex. virage
  serré légitime déclenchant D1-c, deux vols au même indicatif par coïncidence de données rejouées).
  Exigé par le critère de sortie INC-5 et utile au réglage des seuils.
- **Faux négatifs attendus et assumés** : V1 vus par D1 seul, V3 largement (voir limites).

Livrable chiffré : un **CSV/JSON** de résultats + un tableau de synthèse repris dans le rapport (INC-6).

---

## 8. Paramètres configurables

Centralisés dans `defense/config.example.toml` (chargé par un petit module de config) :

- **Connexion** : `aircraft_url` (`.../aircraft.json`), `truth_url` (harnais uniquement), `poll_interval_s`.
- **Historique** : `history_window_s`, `history_max_frames`, `stale_timeout_s`.
- **Seuils D1** : `max_speed_factor`, `abs_speed_cap_kt`, `track_delta_deg`, `max_accel_kt_s`,
  `max_baro_rate_fpm`, bornes d'enveloppe.
- **Seuils D2** : `dup_callsign_min_sep_nm`, `cluster_min_n`, `census_sigma`/`census_abs`, motifs de callsign.
- **Décision** : pondérations des sous-scores, `decision_threshold`.
- **Évaluation** : scénarios à jouer, durée par scénario (en trames ou secondes), chemin de sortie des résultats.

Les valeurs figées en fin d'incrément sont reportées dans l'ADR-0006 (passage à `Accepté`) ou un ADR dédié (§10).

---

## 9. Risques et limites (à documenter dans le rapport)

1. **V1 est invisible à D1** (cinématique propre plausible) : dépendance totale à D2-a/D2-b. Si un flux
   réel n'exposait pas de doublon de callsign, D2 serait aveugle → d'où l'intérêt mentionné de D3 (MLAT/TDOA),
   **hors périmètre** (récepteur unique, ADR-0006).
2. **V3 difficilement détectable par plausibilité** : un faux 7700 est indiscernable d'un vrai par la seule
   cinématique/métadonnée disponible. Au mieux : signaler un **changement abrupt** de squawk vers un code
   d'urgence sans corrélat de phase/manœuvre. Rappel attendu limité — **à assumer explicitement** dans les métriques.
3. **D2-f (NIC/NAC/SIL, RSSI) non discriminant** sur ce banc (champs absents/uniformes dans le flux proxy) :
   contrôle conservé « pour flux réel », exclu des métriques principales.
4. **Faux positifs sur manœuvres légitimes** (D1-c/D1-d) et sur données de rejeu bruitées : seuils à régler,
   FP à cataloguer.
5. **Synchronisation détecteur/harnais en mode rejeu** (une trame par requête) : risque de désalignement
   trame ↔ vérité ; protocole §6.2 et test dédié §11.
6. **Latence/charge** sous V4 (jusqu'à 500 fantômes, garde-fou `v4_flood.MAX`) : vérifier que le détecteur
   tient la cadence.

---

## 10. Décisions méritant un ADR (à rédiger par l'orchestrateur)

1. **ADR-0013 — Intégration du détecteur de défense (point de prélèvement et séparation).**
   *Décision proposée :* le détecteur est un **module séparé `defense/`** qui prélève le flux au niveau
   **`GET /aircraft.json` du proxy** (même entrée que co-atc), en Python, sans dépendance au code du proxy
   ni de co-atc ; la vérité terrain reste cantonnée au harnais d'évaluation. *Alternative écartée :* lire
   l'API interne `/api/v1` de co-atc (couplage, renommage de champs). (Déjà annoncé comme ADR-0013 dans
   `architecture.md §6`.)
2. **ADR-0006 → `Accepté`** : y consigner les **seuils D1/D2 figés** et le modèle d'agrégation/score retenus
   après mesure (le « Suivi » de l'ADR le prévoit). Si les seuils/paramètres méritent leur propre trace
   d'expérimentation (comme ADR-0012 l'a fait pour les attaques), ouvrir un **ADR-0014 — Paramètres et seuils
   du détecteur**.
3. **Extension d'ADR-0011 (optionnelle)** : préciser la **définition de la classe positive** (synthétique
   *vs* réel manipulé) et la **règle d'appariement** `hex` utilisées pour précision/rappel, pour que la
   mesure soit reproductible et non contestable.

---

## 11. Structure des fichiers à créer

```
defense/                         # module séparé — aucun fichier de co-atc ni d'attack-proxy modifié
  README.md                      # but, lancement, config co-atc/proxy à appliquer, exemples
  config.example.toml            # URLs, cadences, seuils D1/D2, pondérations, scénarios
  config.py                      # chargement/validation de la config (dataclass)
  client.py                      # client HTTP : GET aircraft.json (enveloppe ADR-0009) -> list[dict]
  track_history.py               # historique glissant par hex (positions, gs, track, alt, t) + purge
  d1_kinematics.py               # contrôles D1-a…D1-f -> sous-scores + raisons
  d2_metadata.py                 # contrôles D2-a…D2-f (trame + voisinage) -> sous-scores + raisons
  scoring.py                     # agrégation sous-scores -> penalty [0,1] + verdict (seuil)
  detector.py                    # orchestre history + D1 + D2 + scoring sur une trame -> verdicts
  poller.py                      # service : boucle de poll aircraft.json -> detector -> journal/affichage
  truth_client.py                # GET /api/truth -> étiquettes (UNIQUEMENT importé par evaluate)
  evaluate.py                    # harnais : aircraft.json + truth -> apparie -> TP/FP/FN/TN
  metrics.py                     # précision/rappel/F1 par scénario + sérialisation CSV/JSON
  scenarios.py                   # pilotage reproductible via POST /api/attack du proxy (V1..V4)
  results/                       # sorties d'évaluation (CSV/JSON, journaux) — gitignoré si volumineux
  tests/                         # tests unitaires des contrôles (voir §12)
```

**Dépendance structurelle clé :** `truth_client.py` n'est importé **que** par `evaluate.py`.
`detector.py`/`poller.py` n'y font jamais référence (garantit l'invariant §1.2). Un test (§12) le vérifie.

---

## 12. Points de test (critère de démonstrabilité)

- **Unitaires D1** : trame synthétique avec saut de position > plafond → D1-a déclenche ; déplacement
  orthogonal au `track` → D1-b ; `Δgs` brutal → D1-c ; `baro_rate` aberrant → D1-d.
- **Unitaires D2** : deux hex même `flight` éloignés → D2-a ; grappe de N → D2-b ; lot `GH####`/`alt=30000`
  → D2-c ; pic de nouvelles pistes → D2-d.
- **Invariant de séparation** : test statique/convention vérifiant que `detector.py`/`poller.py`
  n'importent pas `truth_client`/`/api/truth`.
- **Intégration hors-ligne** : proxy en **mode rejeu** (`data/sample_replay.json`) + détecteur + harnais ;
  activer V1, V2, V4 tour à tour via `scenarios.py` ; vérifier que les tableaux précision/rappel se remplissent.
- **Synchronisation rejeu** : vérifier l'alignement trame ↔ vérité (§6.2) ; sinon basculer en source stable.
- **Non-régression périmètre** : `git status` montre des changements **uniquement** sous `defense/`
  (porte conformité, [ADR-0008](adr/0008-controle-conformite-et-approbations.md)).

---

## 13. Critère de sortie INC-5 et mise à jour de la roadmap

- **DoD** (roadmap INC-5) : tableau **précision/rappel par scénario V1–V4, avant/après défense**, avec
  **faux positifs documentés**, produit par `evaluate.py` sur le rejeu hors-ligne ; module en dossier séparé ;
  co-atc intact.
- **Porte conformité** : module séparé, co-atc core intact, aucun secret versionné.
- **Suite** : passer ADR-0006 à `Accepté` (seuils figés), créer ADR-0013 (et éventuellement ADR-0014),
  mettre à jour `docs/cahier_des_charges_fonctionnel.md` (EF-30/31/32 : ⬜ → ✅) et la colonne Statut
  de `docs/roadmap.md` (INC-5 : À faire → En cours → Terminé). Alimente INC-6 (rapport/démo).
```
