# ADR-0007 — Proxy d'attaque Python intermédiaire (co-atc mono-source)

- **Statut :** Accepté
- **Date :** 2026-11-09
- **Décideurs :** Auteur(s)
- **Précise :** ADR-0003 (injection par faux récepteur HTTP)

## Contexte

On souhaite une application web Python pour **piloter chaque attaque** sans modifier co-atc. L'idée initiale était d'ajouter cette application comme **source secondaire** simultanée.

Vérification dans le code : co-atc est **mono-source**. `Client.fetchBySource` (`internal/adsb/client.go`) fait un `switch` sur une seule valeur `source_type` (`external-rapidapi`, `external-opensky`, `tar1090`, `readsb-api`, `readsb-file`). Aucune ingestion simultanée de deux flux n'existe. Le commit « multi-source » n'ajoutait que le *choix* du type et sa validation.

De plus :
- `tar1090` exige `aircraft.json` **+ `receiver.json` + `stats.json`** (échec si l'un manque).
- `readsb-api` ne lit **qu'une seule URL** (`fetchReadsbAPIData` → `fetchStandardAircraftURL`), sans receiver/stats.

## Décision

Interposer un **proxy d'attaque Python** entre la source ADS-B réelle et co-atc :

1. Le proxy **récupère** le flux réel (OpenSky anonyme, tar1090, ou rejeu d'une base `data/*.db`).
2. Il applique un **moteur d'attaques** (V1 clonage, V2 trajectoire, V3 squawk, V4 flooding) pilotable.
3. Il **ré-expose** un `aircraft.json` (format dump1090) sur un endpoint HTTP local.
4. co-atc est configuré avec **`source_type = "readsb-api"`** et `readsb_api_url = http://127.0.0.1:<port>/aircraft.json`.

Une **interface web de pilotage** (même application) permet d'activer/paramétrer chaque attaque en direct pendant la démo. co-atc reste **non modifié**.

## Alternatives envisagées

- **Source secondaire simultanée** — impossible (mono-source).
- **Cible `tar1090`** — faisable mais impose d'émuler 3 fichiers ; `readsb-api` (1 endpoint) est plus simple.
- **Rejeu `readsb-file` (fichiers sur disque)** — possible en secours hors-ligne, mais le mode HTTP est plus réaliste et pilotable à chaud.

## Conséquences

- Positives : co-atc intact ; attaques sur du trafic **réel** cloné ; un seul endpoint à servir ; bascule démo propre (basculer la config `source_type`).
- Négatives : le proxy doit suivre la cadence `fetch_interval_seconds` de co-atc ; latence ajoutée (fetch réel → transforme → sert).
- Suivi : ADR-0008 (contrat du flux `aircraft.json` et champs minimaux) ; mesurer l'impact de la latence sur la fraîcheur des pistes.
