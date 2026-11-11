# ADR-0009 — Contrat du flux `aircraft.json` servi par le proxy

- **Statut :** Accepté
- **Date :** 2026-11-09
- **Décideurs :** Auteur(s)
- **Pré-requis de :** INC-1 (proxy transparent)

## Contexte

Le proxy (ADR-0007) doit servir un `aircraft.json` que co-atc ingère via `source_type=readsb-api`. Pour que les pistes s'affichent correctement, le format doit respecter ce qu'attend co-atc. Référence : struct `ADSBTarget` (`internal/adsb/models.go`) et conversion OpenSky `mapOpenSkyStateToTarget` (`internal/adsb/client.go`).

## Décision

Le proxy sert une **enveloppe dump1090** :

```json
{ "now": 1731100000.0, "messages": 1234, "aircraft": [ /* cibles */ ] }
```

- `now` : horodatage Unix en **secondes** (float).
- `aircraft` : liste de cibles.

**Champs d'une cible** (noms JSON exacts) :

| Champ | Type | Obligatoire | Note |
|---|---|---|---|
| `hex` | string | **oui** | clé d'identité, minuscules ; vide = cible ignorée |
| `flight` | string | recommandé | indicatif (callsign) |
| `lat`, `lon` | number | recommandé | sans position, pas de plot sur la carte |
| `alt_baro` | number \| `"ground"` | recommandé | pieds ; accepte la chaîne `"ground"` |
| `gs` | number | recommandé | vitesse sol (nœuds) |
| `track` | number | recommandé | route (degrés) |
| `baro_rate` | number | optionnel | taux vertical (ft/min) |
| `alt_geom` | number | optionnel | altitude géométrique (pieds) |
| `squawk` | string | optionnel | code transpondeur (ex. `"7500"`) |
| `seen` | number | recommandé | secondes depuis dernier message ; **≈ 0 = frais** |
| `messages` | number | optionnel | compteur de messages |
| `rssi` | number | optionnel | puissance signal (dBFS) |

Règles :
- `seen` doit rester **inférieur à `signal_lost_timeout_seconds`** (60 s par défaut), sinon la cible est marquée « signal perdu ».
- Le champ `source_type` est **réécrit par co-atc** (`readsb-api`) : inutile de le fournir.
- Les champs absents sont tolérés (pointeurs nil / `null`). On ne fournit que l'utile.

## Alternatives envisagées

- **Émuler tar1090 (3 fichiers)** — écarté (ADR-0007) : `readsb-api` n'exige que cette seule enveloppe.
- **Fournir tous les champs `ADSBTarget`** — inutile : seul le sous-ensemble ci-dessus influe sur l'affichage et la détection.

## Conséquences

- Positives : contrat minimal et stable ; le générateur de clones n'a qu'à produire ces champs.
- Négatives : si co-atc évolue, revalider le contrat contre `ADSBTarget`.
- Suivi : INC-1 vérifie la parité d'affichage proxy vs source directe.
