# Proxy d'attaque ADS-B

Application d'attaque du banc d'essai ADS-B. Elle s'interpose entre la source
ADS-B réelle et co-atc (voir [`../docs/architecture.md`](../docs/architecture.md),
ADR-0007 et ADR-0009). **co-atc n'est pas modifié ; aucune émission RF.**

## État : INC-1 (pass-through)

À ce stade le proxy **relaie** le trafic sans l'altérer, pour prouver
l'interposition. Les attaques V1–V4 s'ajouteront aux incréments suivants.

## Installation

```bash
cd attack-proxy
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Lancement

```bash
uvicorn app:app --host 127.0.0.1 --port 9900
```

- UI de pilotage : http://127.0.0.1:9900/
- Endpoint pour co-atc : http://127.0.0.1:9900/aircraft.json

## Brancher co-atc sur le proxy

Dans `configs/config.toml`, section `[adsb]` :

```toml
source_type   = "readsb-api"
readsb_api_url = "http://127.0.0.1:9900/aircraft.json"
```

(⚠️ changement de config co-atc — à valider avant de l'appliquer, cf. ADR-0008.)

## Source amont (où vient le trafic) — 3 modes (ADR-0010)

Le mode se choisit par **variables d'environnement**, sans toucher au code :

| Mode | Variables | Usage |
|------|-----------|-------|
| `opensky` (défaut) | `PROXY_STATION_LAT`, `PROXY_STATION_LON`, `PROXY_RADIUS_NM` | Données **live** autour de la station |

> **Authentification OpenSky.** Le mode live s'authentifie en **OAuth2 avec le même
> compte que co-atc** : il lit `../configs/opensky_credentials.json`
> (`clientId`/`clientSecret`). Sans cela, l'accès anonyme est rate-limité (HTTP 429)
> et aucune donnée n'est collectée. Overrides : `PROXY_OPENSKY_AUTH_MODE`
> (`oauth2`/`anonymous`), `PROXY_OPENSKY_CREDS`, `PROXY_OPENSKY_TOKEN_URL`.
> Le secret n'est jamais journalisé.
| `replay_file` | `PROXY_REPLAY_FILE` | **Rejeu hors-ligne** d'un fichier de trames (démo sans réseau) |
| `passthrough_url` | `PROXY_PASSTHROUGH_URL` | Relais d'un `aircraft.json` existant (tar1090/readsb) |

Exemples :

```bash
# Live (OpenSky)
uvicorn app:app --host 127.0.0.1 --port 9900

# Rejeu hors-ligne (recommandé pour la démo — aucune dépendance réseau)
PROXY_UPSTREAM_MODE=replay_file \
PROXY_REPLAY_FILE=data/sample_replay.json \
uvicorn app:app --host 127.0.0.1 --port 9900
```

### Fabriquer un fichier de rejeu depuis vos données réelles

```bash
python tools/export_replay.py ../data/co-atc-2026-11-09.db \
    -o data/sample_replay.json --max-frames 600
```

Lit la table `adsb_targets` d'une base co-atc et écrit un rejeu
(`{ "frames": [ {"aircraft":[…]}, … ] }`). Une trame est servie par requête de
co-atc, en boucle.

## Vérité terrain — journalisation par cycle (ADR-0011, INC-5)

Pour évaluer le détecteur de défense (INC-5), le proxy peut écrire, **à chaque
service de `/aircraft.json`**, une ligne JSONL décrivant la **vérité terrain** du
cycle. C'est un artefact d'analyse **hors-bande** : il n'est **jamais** servi à
co-atc, et sert à corréler *a posteriori* les verdicts du détecteur avec ce qui
était réellement faux (précision / rappel).

**Désactivé par défaut** — activé uniquement par la variable d'environnement
`PROXY_TRUTH_LOG` :

| `PROXY_TRUTH_LOG`        | Effet |
|--------------------------|-------|
| *(non définie)*          | aucune journalisation (défaut) |
| `1` / `true` / `on` / `yes` | actif, fichier par défaut `ground_truth.jsonl` |
| `0` / `false` / `off` / `no` | désactivé |
| `/chemin/fichier.jsonl`  | actif, écrit dans ce fichier |

Un chemin relatif est résolu par rapport au dossier `attack-proxy/`. Le fichier
est exclu du dépôt (`.gitignore`).

```bash
# Rejeu + attaques + journalisation de la vérité terrain
PROXY_TRUTH_LOG=1 \
PROXY_UPSTREAM_MODE=replay_file \
PROXY_REPLAY_FILE=data/sample_replay.json \
uvicorn app:app --host 127.0.0.1 --port 9900
```

Chaque ligne JSONL contient :

```json
{
  "ts": "2026-11-09T12:34:56.789+00:00",
  "epoch": 1762691696.789,
  "real_hex": ["a1b2c3", "..."],
  "real_count": 12,
  "decoys":  [{"hex": "...", "clone_of": "a1b2c3", "attack": "v1_clone", "kind": "clone"}],
  "spoofed": [{"hex": "a1b2c3", "attack": "v3_squawk", "kind": "spoofed_squawk", "code": "7700"}],
  "served_count": 48
}
```

- `real_hex` : avions réels de la source amont ce cycle.
- `decoys` : leurres injectés (clones V1 + fantômes V4), avec l'original copié (`clone_of`, `null` pour un fantôme).
- `spoofed` : avions réels falsifiés (position V2 / squawk V3).

L'état courant de la journalisation est aussi visible dans `GET /api/state`
(champ `truth_log`). La vérité terrain du dernier cycle reste lisible via
`GET /api/truth`.

## Attaque ciblée (V5)

En plus des attaques globales V1–V4, l'UI permet de viser **un avion précis** (sélecteur peuplé par le trafic courant) et de choisir l'effet :
- `ghost_frontal` : un aéronef fantôme en collision frontale sur la route de la cible ;
- `forced_landing` : la trajectoire affichée de la cible est prise en main et descend vers l'aéroport (atterrissage forcé) ;
- `both` : les deux.

Inspirée de l'approche alternative `avionphantom`. Tout reste en simulation locale (aucun aéronef réel affecté). Voir ADR-0014.

## Config co-atc fournie

Un fichier prêt à l'emploi pointe co-atc sur le proxy :
`../configs/config.toml.proxy` (`source_type=readsb-api`,
`readsb_api_url=http://127.0.0.1:9900/aircraft.json`). Lancer :

```bash
./bin/co-atc -config configs/config.toml.proxy
```

## Vérifier INC-1 (critère de sortie)

1. Lancer le proxy, ouvrir `/aircraft.json` : on doit voir une enveloppe
   `{"now":…, "aircraft":[…]}` conforme à ADR-0009.
2. Basculer co-atc sur le proxy et comparer l'affichage avec la source directe :
   **même trafic**. Si oui, INC-1 est « Terminé ».

## Structure

```
attack-proxy/
  app.py          # serveur FastAPI : /aircraft.json, /api/state, UI
  upstream.py     # fetch amont (OpenSky / passthrough_url) -> contrat ADR-0009
  attacks/        # moteur (pipeline identité à INC-1 ; V1–V4 ensuite)
  truth_log.py    # journalisation vérité terrain par cycle (hors-bande, ADR-0011)
  state.py        # état partagé (amont + interrupteurs d'attaques)
  requirements.txt
```
