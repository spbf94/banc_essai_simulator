# Proposition de projet — Attaque par clonage ADS-B sur un système de supervision ATC

**Type de document :** Proposition de projet
**Auteur(s) :** à compléter

| | |
|---|---|
| Secteur | Aéronautique — surveillance ADS-B |
| Type de banc | Hybride |
| Plateforme (SUT) | Co-ATC (open source, MIT) |
| Station | CYYZ — Toronto Pearson |
| Vulnérabilités | 4 scénarios (V1 phare + V2–V4) |

> **Portée et éthique.** Toutes les expérimentations se déroulent **en vase clos, au niveau des données décodées** : un émulateur de récepteur alimente notre propre instance de Co-ATC. **Aucune émission radiofréquence réelle** sur la bande aéronautique (1090 MHz) n'est produite, conformément à la réglementation et aux pratiques de laboratoire des travaux de référence [1], [3].

---

## 1. Type de banc d'essai et justification

Nous retenons un banc d'essai **hybride** : le système sous test (SUT) est un logiciel de supervision réel et complet, tandis que la source de surveillance adverse est **simulée au niveau du message**.

Le SUT est **Co-ATC**, une chaîne de supervision ATC open source (Go) qui ingère des données ADS-B, reconstruit les trajectoires, détecte les phases de vol et les conflits de proximité, et affiche le trafic en temps réel sur une carte. C'est un logiciel opérationnel réel, et non un modèle abstrait.

La source de données est **émulée** : un petit serveur HTTP local sert un fichier `aircraft.json` au format `dump1090 / tar1090`, exactement la sortie qu'un récepteur SDR produirait après décodage des trames 1090ES. Injecter à ce niveau reproduit fidèlement le *résultat* d'une attaque par émission malveillante, tout en restant répétable, isolé et légal.

**Pourquoi l'hybride plutôt que la simulation ou l'émulation pures.** Une émulation complète (émetteur SDR → ondes → récepteur) exigerait une cage de Faraday et resterait juridiquement sensible, pour un gain limité sur l'étude des contre-mesures applicatives. Une simulation pure (un modèle de trafic type [5]) ne mettrait à l'épreuve aucun logiciel de supervision réel. L'hybride conserve le réalisme du SUT et la précision des impacts observés, tout en offrant le contrôle et la reproductibilité de l'injection par données.

---

## 2. Infrastructure, architecture et choix d'attaque

### Architecture considérée

Le flux nominal de Co-ATC relie la source ADS-B à la carte opérateur en passant par la détection de conflits et de phases. Notre banc insère un **émulateur de récepteur contrôlé par l'attaquant** en amont, à la place du récepteur légitime.

```
┌──────────── ATTAQUANT (notre code) ────────────┐      ┌─────── SUT — CO-ATC (non modifié) ───────┐
│  Flux de référence (rejeu .db / OpenSky)        │      │  Ingestion ADS-B                          │
│          │                                      │      │        │                                 │
│          ▼                                      │ HTTP │        ▼                                 │
│  Générateur de clones (forge les leurres)       │─────▶│  Conflits / phases ──▶ Carte opérateur   │
│          │                                      │      │        │                                 │
│          ▼                                      │      │        ▼                                 │
│  Faux récepteur HTTP (sert aircraft.json)       │      │  [Détecteur de plausibilité D1/D2]       │
└─────────────────────────────────────────────────┘      └──────────────────────────────────────────┘
          Co-ATC configuré avec source_type = "tar1090" → URL du faux récepteur
```

*Fig. 1 — Insertion de l'émulateur adverse en amont de Co-ATC (`source_type = tar1090`).*

### Hypothèses de travail

- L'ADS-B est diffusé **en clair, sans authentification ni intégrité** : tout récepteur accepte toute trame bien formée [1], [2].
- L'attaquant peut **injecter et altérer des messages décodés** ; côté effet sur le SUT, cela équivaut à un émetteur 1090ES malveillant [3].
- La station dispose d'un **récepteur unique** : aucune multilatération native pour recouper les positions.
- Au départ, Co-ATC n'applique **aucune contre-mesure** ; la défense est ajoutée en seconde phase.

### Vulnérabilités et cyberattaques retenues

Toutes découlent de l'absence d'authentification du canal. L'attaque phare est le **clonage** : pour chaque avion réel, on émet plusieurs copies portant le même indicatif et le même type, à des positions, caps et altitudes décalés. L'opérateur voit alors des étiquettes identiques en plusieurs endroits et **ne peut plus distinguer l'aéronef réel de ses leurres**.

| Réf. | Vulnérabilité / attaque | Impact visé sur Co-ATC | Appui |
|---|---|---|---|
| **V1** *(phare)* | **Clonage d'aéronefs (essaim de leurres)** — duplication des avions réels à trajectoires divergentes | Confusion opérateur, fausses cibles indiscernables, empoisonnement du contexte IA | [2], [3] |
| **V2** | **Spoofing de trajectoire** — dérive progressive de la position d'un clone | Fausse route, fausse phase de vol, fausse alerte de proximité | [1], [3] |
| **V3** | **Faux squawk d'urgence** — injection de 7500 / 7600 / 7700 | Fausse urgence, réaction opérationnelle indue | [2], [4] |
| **V4** | **Saturation (DoS d'affichage)** — centaines de cibles injectées | Dégradation de la carte et de la logique d'alerte | [3], [4] |

### Défenses étudiées

- **D1 — Plausibilité cinématique.** Rejet des cibles dont le mouvement sort du domaine de vol : vitesse, accélération et taux de montée hors bornes, sauts de position incompatibles avec la vitesse maximale, incohérence cap/vecteur. S'appuie sur les modules `physics` et de prédiction de trajectoire déjà présents dans Co-ATC.
- **D2 — Cohérence des métadonnées.** Détection des signatures d'injection : indicatif dupliqué à plusieurs positions, adresse ICAO émise en deux endroits (« téléportation »), champs d'intégrité (`NIC/NAC/SIL`) et `RSSI` uniformes ou incohérents sur les leurres.
- **D3 — Recoupement multi-source *(discutée, non implémentée)*.** Multilatération / TDOA sur plusieurs récepteurs synchronisés et comparaison à une source indépendante (OpenSky) [1], [3]. Voir §4.

---

## 3. Outils et matières utilisés

- **Co-ATC** (licence MIT) comme SUT — `github.com/yegors/co-atc` [6]. Aucune modification du cœur pour l'attaque ; le détecteur de défense est ajouté en module séparé.
- **Émulateur de récepteur + générateur de clones** : initiative du projet (Go ou Python), produisant un `aircraft.json` au format dump1090.
- **Flux de référence** : rejeu d'une base Co-ATC enregistrée (`data/co-atc-*.db`) ou flux OpenSky anonyme, servant de trafic « légitime » à cloner.
- **Articles de référence** [1]–[5] pour le modèle de menace, les attaques et les contre-mesures.

Le projet **part de l'existant** (Co-ATC + littérature) ; l'apport propre est l'émulateur adverse, la variante de clonage et le détecteur de plausibilité.

---

## 4. Limites anticipées et suggestions d'amélioration

**Limites**

- Pas de couche RF/physique : le décodage, les collisions de trames et le brouillage PHY ne sont pas testés.
- Injection au niveau `aircraft.json` (déjà fusionné), non à la trame `DF17` brute : fidélité partielle.
- Récepteur unique : la MLAT ne peut être démontrée, seulement discutée.
- Faux positifs possibles du détecteur sur des manœuvres brusques mais légitimes.

**Suggestions d'amélioration**

- Monter en fidélité en générant de vraies trames `DF17` rejouées via un décodeur (dump1090) en boucle fermée.
- Étape future avec SDR en cage de Faraday pour couvrir la couche RF.
- Ajouter un second récepteur virtuel pour prototyper une MLAT simplifiée (amélioration à [1], [3]).
- Croiser plusieurs sources indépendantes pour pondérer la confiance des pistes.

---

## Références *(IEEE)*

1. M. Strohmeier, M. Schäfer, R. Pinheiro, V. Lenders, and I. Martinovic, "On Perception and Reality in Wireless Air Traffic Communication Security," *IEEE Transactions on Intelligent Transportation Systems*, vol. 18, no. 6, pp. 1338–1357, 2017.
2. A. Costin and A. Francillon, "Ghost in the Air (Traffic): On insecurity of ADS-B protocol and practical attacks on ADS-B devices," *Proceedings of Black Hat USA*, no. 8, pp. 1–12, 2012.
3. M. Schäfer, V. Lenders, and I. Martinovic, "Experimental Analysis of Attacks on Next Generation Air Traffic Communication," in *Proc. Int. Conf. on Applied Cryptography and Network Security (ACNS)*, pp. 253–271, 2013.
4. S. Amin, T. Clark, R. Offutt, and K. Serenko, "Design of a cyber security framework for ADS-B based surveillance systems," in *2014 Systems and Information Engineering Design Symposium (SIEDS)*, 2014, pp. 304–309.
5. M. Monteiro, T. Sarmento, A. Barreto, P. Costa, and M. Hieb, "An integrated mission and cyber simulation for Air Traffic Control," in *2016 IEEE 19th Int. Conf. on Intelligent Transportation Systems (ITSC)*, 2016, pp. 2687–2692.
6. Dépôt GitHub « Co-ATC », `github.com/yegors/co-atc`, consulté le 8 nov. 2026. *(Vérifier/compléter le nom de l'auteur.)*

> **Note de rédaction.** Les références inventées sont à proscrire : toutes celles ci-dessus proviennent de la liste de référence, sauf [6] (le dépôt du logiciel), à confirmer.
