# ADR-0003 — Injection par faux récepteur HTTP (tar1090)

- **Statut :** Accepté
- **Date :** 2026-11-08
- **Décideurs :** Auteur(s)

## Contexte

Il faut un point d'injection des cibles falsifiées dans Co-ATC. Le client ADS-B de Co-ATC gère plusieurs sources (`internal/adsb/client.go`), dont `tar1090`/`readsb-api` qui lisent un `aircraft.json` depuis une URL. Le service fusionne ensuite les cibles avant `ProcessRawData` (`internal/adsb/service.go:549`).

## Décision

Faire tourner un **serveur HTTP local « faux récepteur »** qui sert un `aircraft.json` fabriqué, et configurer Co-ATC avec `source_type = "tar1090"` pointant sur ce serveur. Co-ATC **n'est pas modifié** pour l'attaque.

## Alternatives envisagées

- **Étendre `internal/simulation`** — écarté comme vecteur principal : plafonné à 10 avions (`MaxSimulatedAircraft`), cibles marquées `type:"sim"`, champs limités (pas de squawk ni de champs d'intégrité). Utile seulement comme appoint.
- **Injecter dans le WebSocket de sortie** — écarté : court-circuite la logique de détection qu'on veut justement tester.

## Conséquences

- Positives : réalisme (chemin d'ingestion réel exercé), aucune modification du cœur, contrôle total des champs (hex, squawk, NIC/NAC, RSSI…).
- Négatives : injection au niveau fusionné, pas à la trame brute DF17 (limite de fidélité, cf. ADR-0002).
- Suivi : produire l'émulateur + le générateur de clones comme apport propre du projet.
