# ADR-0010 — Sources amont du proxy (live / rejeu fichier / passthrough)

- **Statut :** Accepté
- **Date :** 2026-11-09
- **Décideurs :** Auteur(s)
- **Précise :** ADR-0007 (proxy), ADR-0009 (contrat), lié à la robustesse de la démo

## Contexte

Le proxy doit pouvoir fonctionner **même sans accès aux données live**. OpenSky anonyme est rate-limité (429) et OpenSky OAuth2 dépend du réseau le jour de la démo. Pour la reproductibilité (démonstration), il faut une source **hors-ligne** à partir de données historiques. Les bases `data/co-atc-*.db` contiennent une table `adsb_targets` (hex, lat, lon, alt_baro, gs, track, squawk, timestamp…) directement rejouable.

## Décision

Le proxy accepte **trois modes de source amont**, sélectionnables sans modifier le code (variables d'environnement) :

1. **`opensky`** — données live, zone autour de la station (OAuth2/anonyme).
2. **`replay_file`** — rejeu d'un fichier de trames historiques (hors-ligne, reproductible). Format : JSON `{ "frames": [ { "aircraft": [ …contrat ADR-0009… ] }, … ] }`. Une trame est servie par requête de co-atc, en boucle.
3. **`passthrough_url`** — relais d'un `aircraft.json` existant (tar1090/readsb).

Un script `tools/export_replay.py` exporte un fichier de rejeu depuis une base `data/*.db` (groupage par horodatage → trames).

## Alternatives envisagées

- **Live uniquement** — écarté : fragile (429, réseau), démo non reproductible.
- **Lire la base SQLite directement depuis le proxy à l'exécution** — écarté : couple le proxy au schéma co-atc ; un fichier de rejeu exporté est autonome et portable.

## Conséquences

- Positives : simulation possible sans réseau ; démo reproductible ; mêmes attaques applicables sur du rejeu ou du live.
- Négatives : le rejeu reflète un instantané passé (trafic figé dans le temps du fichier) ; la densité/fraîcheur dépend de l'export.
- Suivi : la vérité terrain des leurres (pour évaluer la défense, INC-5) est connue puisque le rejeu de base ne contient que des avions « réels ».
