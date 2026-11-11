# Cahier des charges fonctionnel — banc d'essai ADS-B

**Point d'entrée unique** décrivant ce que fait notre environnement et les solutions retenues. Tenu à jour au fil de l'avancement. Documents liés : [architecture](architecture.md), [roadmap](roadmap.md), [ADR](adr/README.md).

- **Dernière mise à jour :** 2026-11-09
- **Projet :** banc d'essai hybride de cybersécurité, secteur aéronautique (ADS-B)
- **Statut global :** INC-0 terminé (co-atc en marche) · INC-1/INC-2 en cours (proxy + UI)

---

## 1. Objet et périmètre

Évaluer, en vase clos, l'impact d'attaques exploitant l'absence d'authentification du protocole ADS-B sur un système de supervision ATC réel (co-atc), puis éprouver une défense. **Aucune émission radiofréquence** : l'injection se fait au niveau des données décodées ([ADR-0004](adr/0004-contrainte-ethique-pas-de-rf.md)).

## 2. Acteurs

| Acteur | Rôle |
|--------|------|
| Opérateur co-atc | Observe la carte temps réel (cible de la tromperie) |
| Attaquant-pilote | Pilote la source et les attaques via l'UI du proxy |
| Évaluateur | Rejoue la démo, consulte résultats et documentation |

## 3. Vue d'ensemble de l'environnement

```
Source (live OpenSky | rejeu fichier | passthrough)
      → PROXY d'attaque (moteur + UI de pilotage) → co-atc (readsb-api) → carte
                                                        → Détecteur (défense, à venir)
```

Trois sous-ensembles : **co-atc** (SUT, non modifié), **proxy d'attaque** (notre apport), **détecteur de défense** (notre apport, à venir).

## 4. Exigences fonctionnelles

Statuts : ✅ fait · 🔶 en cours · ⬜ à venir.

### 4.1 Supervision (co-atc — réutilisé)

| # | Exigence | Statut | Solution |
|---|----------|--------|----------|
| EF-01 | Ingérer une source ADS-B et afficher le trafic en temps réel | ✅ | co-atc, source OpenSky OAuth2 |
| EF-02 | Détecter phases de vol, conflits de proximité, pistes en service | ✅ | modules `adsb` de co-atc |
| EF-03 | Basculer la source sans modifier co-atc | ✅ | `source_type=readsb-api` vers le proxy ([ADR-0007](adr/0007-proxy-intermediaire-python.md)) |

### 4.2 Proxy — source de données

| # | Exigence | Statut | Solution |
|---|----------|--------|----------|
| EF-10 | S'interposer entre la source réelle et co-atc | ✅ | endpoint `GET /aircraft.json` (contrat [ADR-0009](adr/0009-contrat-aircraft-json.md)) |
| EF-11 | Utiliser une source **live** (OpenSky) authentifiée | ✅ | mode `opensky` en **OAuth2**, même compte que co-atc (`configs/opensky_credentials.json`) — évite le 429 |
| EF-12 | Utiliser des **données historiques** rejouées hors-ligne | ✅ | mode `replay_file` + `tools/export_replay.py` (depuis `data/*.db`) |
| EF-13 | Relayer un `aircraft.json` existant | ✅ | mode `passthrough_url` |
| EF-14 | **Choisir la source (historique/live) depuis l'UI web** | ✅ | sélecteur + `POST /api/source` |

### 4.3 Proxy — attaques et pilotage

| # | Exigence | Statut | Solution |
|---|----------|--------|----------|
| EF-20 | **Choisir l'attaque depuis l'UI**, avec une brève **description** | ✅ | cartes d'attaque (label + description + interrupteur) |
| EF-21 | Activer/désactiver chaque attaque à chaud | ✅ | `POST /api/attack/{key}/{on\|off}` |
| EF-22 | V1 — Clonage d'aéronefs (avion réel dupliqué en N leurres) | ✅ | `attacks/v1_clone.py` — leurres stables, même indicatif, hex plausibles |
| EF-27 | Vérité terrain hors-bande (quels leurres, copie de quel réel) | ✅ | `GET /api/truth` + liste dans l'UI ([ADR-0011](adr/0011-verite-terrain-et-evaluation.md)) — co-atc ne la voit pas |
| EF-28 | Mode « révélation » activable/désactivable : marque les leurres d'un préfixe `->` sur l'indicatif **dans co-atc** | ✅ | interrupteur UI + `POST /api/reveal/{on\|off}` ; OFF par défaut (attaque réaliste) |
| EF-23 | V2 — Spoofing de trajectoire (dérive position avion réel) | ✅ | `attacks/v2_trajectory.py` |
| EF-24 | V3 — Faux squawk d'urgence (7500/7600/7700) | ✅ | `attacks/v3_squawk.py` (code réglable dans l'UI) |
| EF-25 | V4 — Saturation (DoS d'affichage) | ✅ | `attacks/v4_flood.py` (fantômes mobiles) |
| EF-26 | Visualiser l'état (mode, cibles servies, erreurs) | ✅ | barre de statut de l'UI |
| EF-29 | V5 — Attaque ciblée sur un avion précis (fantôme frontal / atterrissage forcé) | ✅ | `attacks/v5_targeted.py` ; sélecteur d'avion cible + mode dans l'UI ([ADR-0014](adr/0014-attaque-ciblee-v5.md)) |

### 4.4 Défense

| # | Exigence | Statut | Solution |
|---|----------|--------|----------|
| EF-30 | Détecter les cibles implausibles (D1 cinématique) | ✅ | `defense/detector.py` (résidu nav. à l'estime, fenêtre glissante) |
| EF-31 | Détecter les incohérences de métadonnées (D2) | ✅ | indicatif dupliqué sur hex distincts, squawk urgence, cohorte flood |
| EF-32 | Mesurer précision/rappel par scénario | ✅ | `defense/evaluate.py` — F1 V4=1.00, V3=0.98, V1=0.82, V2=0.68 ; FP base 0,2 % |

### 4.5 Exploitation / démo

| # | Exigence | Statut | Solution |
|---|----------|--------|----------|
| EF-40 | Démo reproductible sans réseau | ✅ (base) | mode rejeu + fichier exporté |
| EF-41 | Configs prêtes : Toronto / Montréal / Proxy | ✅ | `config.toml`, `config.toml.montreal`, `config.toml.proxy` |
| EF-42 | Rapport et présentation conformes aux exigences | 🔶 | rapport LaTeX : Expérimentation + Remédiation remplies avec les résultats réels d'INC-5 ; reste titre/figures/compilation |

## 5. Contraintes (non fonctionnelles clés)

- Aucune émission RF ; tout en localhost / réseau de labo.
- co-atc non modifié ; code d'attaque et de défense dans des dossiers séparés.
- Aucun secret versionné ; références réelles uniquement.
- Contrôle de conformité des agents ([ADR-0008](adr/0008-controle-conformite-et-approbations.md)).

## 6. Journal de révision

| Date | Évolution |
|------|-----------|
| 2026-11-09 | Création. co-atc opérationnel (OAuth2) ; proxy 3 sources + export rejeu ; UI de pilotage (source + attaques décrites). Attaques et défense à venir. |
| 2026-11-09 | Correctif : le mode live du proxy s'authentifie désormais en OAuth2 (compte partagé avec co-atc) ; collecte de vols validée (jeton obtenu + états reçus). |
| 2026-11-09 | INC-3 : attaque V1 clonage opérationnelle (leurres stables, même indicatif) + vérité terrain hors-bande (`/api/truth`, mode « révéler »). Testé hors-ligne sur le rejeu. |
| 2026-11-09 | V1 affiné : trajectoires **divergentes** par leurre (cinématique propre, navigation à l'estime) au lieu de parallèles ; `signal_lost_timeout_seconds=15` dans config.toml.proxy pour un effacement plus rapide des leurres après décochage. |
| 2026-11-09 | INC-4 : V2 (dérive de position), V3 (squawk d'urgence réglable), V4 (flood de fantômes) ; UI avec contrôles de paramètres et choix trajectoires divergentes/parallèles pour V1. Testé hors-ligne. |
| 2026-11-09 | INC-5 : détecteur D1/D2 (`defense/`) + évaluation ; ADR-0006 accepté, ADR-0013 (intégration). Mode révélation `->` des leurres dans co-atc (EF-28). 6 agents exécutés (recherche, archi, attaque, défense, rapport, conformité). |
| 2026-11-09 | INC-5 vérifié (détecteur réexécuté, métriques reproduites). Rapport complété : tableau Expérimentation + Remédiation avec F1 réels, [5] Monteiro citée. Réserves restantes : compilation pdflatex (Overleaf), noms d'équipe, export PNG des schémas. |
| 2026-11-09 | V5 : attaque ciblée (inspirée de l'approche alternative avionphantom) — avion cible paramétrable, ghost frontal + atterrissage forcé (descente vers l'aéroport), pilotable depuis l'UI. Testé hors-ligne. |
