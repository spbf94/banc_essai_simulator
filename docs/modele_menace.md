# Modèle de menace ADS-B — banc d'essai co-atc

Synthèse du modèle de menace de la surveillance coopérative ADS-B, destinée à nourrir
les sections **Contexte** et **Choix et exploitation de la vulnérabilité** du rapport.

- **Dernière mise à jour :** 2026-11-09
- **Portée :** attaques au niveau du message décodé (pas de couche RF), conformément au
  banc hybride ([ADR-0002](adr/0002-type-de-banc-hybride.md), [ADR-0004](adr/0004-contrainte-ethique-pas-de-rf.md)).
- **Règle de citation :** chaque fait renvoie à l'une des références **[1]–[5]** de la
  [proposition](proposition_projet_adsb.md). **Aucune autre source n'est invoquée** ; le
  les références inventées sont à proscrire.

> Les cinq références, telles que listées dans la proposition :
> **[1]** Strohmeier, Schäfer, Pinheiro, Lenders, Martinovic, *On Perception and Reality
> in Wireless Air Traffic Communication Security*, IEEE T-ITS, 2017.
> **[2]** Costin & Francillon, *Ghost in the Air (Traffic): On insecurity of ADS-B
> protocol and practical attacks on ADS-B devices*, Black Hat USA, 2012.
> **[3]** Schäfer, Lenders, Martinovic, *Experimental Analysis of Attacks on Next
> Generation Air Traffic Communication*, ACNS, 2013.
> **[4]** Amin, Clark, Offutt, Serenko, *Design of a cyber security framework for ADS-B
> based surveillance systems*, SIEDS, 2014.
> **[5]** Monteiro, Sarmento, Barreto, Costa, Hieb, *An integrated mission and cyber
> simulation for Air Traffic Control*, ITSC, 2016.

---

## 1. Contexte : pourquoi l'ADS-B est attaquable

L'ADS-B (Automatic Dependent Surveillance–Broadcast) diffuse en clair, sur 1090 MHz
(1090ES / DF17), la position, la vitesse et l'identité de chaque aéronef, **sans
chiffrement, sans authentification ni contrôle d'intégrité** : tout récepteur accepte
toute trame bien formée [1], [2]. Le protocole a été conçu pour la fiabilité et
l'interopérabilité, pas pour résister à un adversaire ; la littérature souligne cet écart
entre la perception du risque et la réalité technique [1].

Trois propriétés exploitées par l'attaquant :

- **Diffusion ouverte** — n'importe qui équipé d'un récepteur peut écouter (eavesdropping)
  et n'importe qui équipé d'un émetteur bon marché (SDR) peut injecter des trames
  crédibles ; Costin & Francillon ont montré la faisabilité et le faible coût de ces
  attaques en pratique [2].
- **Absence d'authentification de l'émetteur** — rien ne lie une trame à un aéronef réel ;
  l'adresse ICAO 24 bits est déclarative et falsifiable [2], [3].
- **Confiance implicite du récepteur** — le décodeur et la chaîne de supervision traitent
  les cibles forgées comme légitimes ; Schäfer et al. ont réalisé expérimentalement
  l'injection, la modification et la suppression de messages sur le canal [3].

### Taxonomie des capacités d'attaque (niveau message)

La littérature distingue trois primitives sur le canal, toutes réalisées ou analysées
expérimentalement par Schäfer et al. [3] et discutées par Strohmeier et al. [1] :

| Primitive | Effet | Réf. |
|---|---|---|
| **Injection** de messages | ajouter des cibles/trames inexistantes (avions fantômes) | [1], [2], [3] |
| **Modification** de messages | altérer un champ d'une trame légitime (position, vitesse, squawk) | [1], [3] |
| **Suppression** de messages (brouillage/interférence destructrice) | faire disparaître une cible réelle, saturer le canal | [1], [3] |

À partir de ces primitives, la littérature dérive des **attaques de haut niveau** :
injection/flooding de fantômes, disparition d'aéronef, modification de trajectoire
virtuelle, fausse alarme [1], [2], [3]. Amin et al. cadrent ces menaces dans un modèle de
risque pour la surveillance ADS-B et proposent un cadre de sécurité [4] ; Monteiro et al.
fournissent un environnement de simulation intégrant ces cyber-effets et leur impact sur
la mission ATC [5].

> **Important pour notre banc.** Notre injection se fait au niveau du `aircraft.json`
> décodé (sortie équivalente d'un récepteur SDR). Elle reproduit l'**effet** d'une
> injection/modification RF sur le SUT, sans en reproduire la couche physique [2], [3].
> Les primitives de suppression RF (brouillage, interférence destructrice [3]) ne sont
> donc **pas** couvertes directement ; notre V4 approxime la saturation au niveau
> affichage/logique, pas au niveau radio.

---

## 2. Mapping des attaques documentées vers nos scénarios V1–V4

Rappel des scénarios du banc ([proposition §2](proposition_projet_adsb.md),
[ADR-0005](adr/0005-attaque-phare-clonage.md), [ADR-0012](adr/0012-parametres-experimentation.md)) :
**V1** clonage (phare), **V2** spoofing de trajectoire, **V3** faux squawk d'urgence,
**V4** flooding/DoS d'affichage.

| Scénario | Primitive(s) littérature | Attaque de haut niveau correspondante | Réf. |
|---|---|---|---|
| **V1 — Clonage** | Injection | Injection de fantômes calqués sur du trafic réel (même indicatif/type, hex distincts) | [2], [3] |
| **V2 — Trajectoire** | Injection + modification | Virtual trajectory modification / dérive progressive de position | [1], [3] |
| **V3 — Faux squawk** | Injection / modification de champ | Fausse alarme (faux code d'urgence 7500/7600/7700) | [2], [4] |
| **V4 — Flooding/DoS** | Injection massive | Ghost-aircraft flooding, saturation du système de surveillance | [3], [4] |

### V1 — Clonage d'aéronefs *(attaque phare)*

- **Description.** Pour chaque avion réel, émettre N copies portant le **même indicatif et
  le même type**, à positions/caps/altitudes décalés, avec des adresses ICAO distinctes
  ([ADR-0005](adr/0005-attaque-phare-clonage.md)).
- **Fondement littérature.** C'est une **injection de cibles fantômes** ; sa faisabilité
  pratique à bas coût via SDR est démontrée par Costin & Francillon [2], et l'injection de
  messages crédibles acceptés par la chaîne de réception est établie expérimentalement par
  Schäfer et al. [3]. L'absence d'authentification rend le vrai indiscernable de ses
  leurres [2], [3].
- **Impact sur co-atc.** Étiquettes identiques en plusieurs endroits, confusion de
  l'opérateur, empoisonnement du contexte des modules de détection (conflits/phases) et de
  l'assistance IA. co-atc accepte toute cible du flux sans contrôle de plausibilité (le
  champ indicatif/`hex` n'est pas vérifié contre un référentiel).
- **Sous-cas défensif.** Réutiliser **le même hex ICAO** pour deux positions crée une
  signature de « téléportation » détectable (voir D2) ; conservé comme sous-cas plutôt que
  comme forme principale [ADR-0005].

### V2 — Spoofing de trajectoire

- **Description.** Dérive progressive et physiquement « douce » de la position d'une cible
  (réelle clonée), produisant une fausse route, une fausse phase de vol ou une fausse
  alerte de proximité.
- **Fondement littérature.** Correspond à la **modification de trajectoire virtuelle**
  analysée par Strohmeier et al. [1] et réalisée via injection/modification de messages par
  Schäfer et al. [3]. Une dérive lente reste cinématiquement plausible et donc plus
  difficile à distinguer qu'un saut brutal — point qui motive directement D1 [1], [3].
- **Impact sur co-atc.** Reconstruction de trajectoire faussée, déclenchement potentiel de
  fausses alertes de conflit, décisions opérationnelles indues.

### V3 — Faux squawk d'urgence

- **Description.** Injecter un code transpondeur d'urgence — 7500 (détournement), 7600
  (panne radio), 7700 (urgence générale) — sur une cible.
- **Fondement littérature.** Relève de la **fausse alarme / injection d'un champ critique**
  pour provoquer une réaction opérationnelle ; la capacité de forger des trames portant des
  champs arbitraires est démontrée par Costin & Francillon [2], et la nécessité de traiter
  ce type de menace dans un cadre de sécurité ADS-B est posée par Amin et al. [4].
- **Impact sur co-atc.** Le champ `squawk` est **transmis tel quel** par la chaîne co-atc
  (`internal/adsb/`), sans contrôle de plausibilité ni corrélation : un faux 7700 est donc
  présenté à l'opérateur comme une urgence authentique, déclenchant une réaction indue.

### V4 — Saturation / DoS d'affichage

- **Description.** Injecter des centaines de cibles fantômes mobiles pour dégrader la carte
  et la logique d'alerte (garde-fou `MAX=500`, [ADR-0012](adr/0012-parametres-experimentation.md)).
- **Fondement littérature.** Forme de **ghost-aircraft flooding** : l'injection massive de
  cibles est une déclinaison directe des primitives d'injection établies par Schäfer et al.
  [3], et le déni de service de la surveillance figure parmi les menaces que le cadre
  d'Amin et al. cherche à contenir [4].
- **Impact sur co-atc.** Surcharge visuelle et cognitive, dilution des vraies cibles,
  charge accrue sur les détecteurs de conflits/phases. *Limite :* notre V4 sature au niveau
  **données/affichage**, pas au niveau **RF** (le brouillage/suppression radio de [1], [3]
  n'est pas reproduit).

---

## 3. Contre-mesures proposées par la littérature

Les cinq articles convergent vers des familles de défense complémentaires. Elles sont
reliées ci-dessous à nos défenses prévues **D1** (plausibilité cinématique), **D2**
(cohérence des métadonnées) et **D3** (recoupement multi-source, discutée non implémentée),
cf. [ADR-0006](adr/0006-strategie-defense-plausibilite.md).

| Famille de contre-mesure | Principe | Réf. | Couvre | Notre défense |
|---|---|---|---|---|
| **Vérification de plausibilité physique / cinématique** (filtrage de Kalman, bornes du domaine de vol) | rejeter les mouvements hors domaine de vol et les sauts incompatibles avec la vitesse max | [1], [3] | V1, V2, V4 | **D1** |
| **Recoupement et fusion multi-source / multi-récepteur** (multilatération, TDOA, comparaison à une source indépendante) | localiser indépendamment l'émetteur et comparer à la position annoncée | [1], [2], [3] | V1, V2, V3, V4 | **D3** (discutée) |
| **Détection d'anomalies / cohérence des données et métadonnées** | repérer indicatifs dupliqués, adresses « téléportées », champs d'intégrité/RSSI incohérents | [1], [4] | V1, V3 | **D2** |
| **Authentification / chiffrement du lien** (PKI, signatures) | lier chaque trame à un émetteur légitime | [2], [4] | V1–V4 (racine) | hors périmètre |
| **Simulation / évaluation d'impact** des cyber-effets sur la mission ATC | mesurer l'effet des attaques pour dimensionner les défenses | [5] | V1–V4 | méthode d'éval. |

### Détail par famille

- **Plausibilité cinématique (→ D1).** Strohmeier et al. [1] et Schäfer et al. [3]
  proposent des contrôles de vraisemblance (filtrage de Kalman, cohérence des positions
  successives avec le modèle de vol) pour détecter injections et modifications : une cible
  dont le mouvement sort du domaine de vol, ou qui « saute » plus vite que sa vitesse max,
  est suspecte. Efficace contre V1 (leurres à cinématique propre incohérente), V2 (dérive
  trop rapide) et V4 (fantômes au comportement non physique). **Limite notée par la
  littérature :** un attaquant « physiquement cohérent » (dérive lente, V2) peut échapper à
  D1 [1], [3] — d'où l'intérêt de D2/D3.

- **Recoupement multi-source / MLAT (→ D3).** La multilatération (TDOA sur plusieurs
  récepteurs synchronisés) et la comparaison à une source indépendante sont présentées
  comme la parade la plus robuste à l'injection de fantômes, car elles vérifient la
  **position réelle** de l'émetteur [1], [2], [3]. **Non implémentée** dans notre banc :
  récepteur unique (hypothèse de la proposition), d'où D3 seulement *discutée*
  [ADR-0006].

- **Cohérence des métadonnées / détection d'anomalies (→ D2).** Amin et al. [4] bâtissent
  un cadre de sécurité ADS-B incluant la détection d'anomalies ; Strohmeier et al. [1]
  relèvent la valeur des signaux incohérents. Signatures exploitables, **présentes dans le
  modèle de données co-atc** (`internal/adsb/models.go`, `external.go` : champs `nic`,
  `nac_p`, `nac_v`, `sil`, `rssi`, `squawk`) : indicatif dupliqué à plusieurs positions,
  adresse ICAO émise en deux endroits, champs d'intégrité `NIC/NAC/SIL` ou `RSSI` uniformes
  / incohérents sur les leurres. Efficace contre V1 (clones) et V3 (squawk incohérent avec
  le reste du contexte).

- **Authentification / chiffrement (racine).** Costin & Francillon [2] et Amin et al. [4]
  discutent l'ajout d'authentification/chiffrement comme remède de fond, tout en notant sa
  **difficulté de déploiement rétroactif** sur un protocole normalisé et une flotte
  mondiale. Hors périmètre de notre banc applicatif, mais cité comme cause racine commune à
  V1–V4.

- **Simulation et mesure d'impact.** Monteiro et al. [5] proposent une simulation intégrée
  mission + cyber pour l'ATC, utile pour **évaluer l'impact** des attaques et dimensionner
  les contre-mesures ; cadre méthodologique de référence pour notre évaluation
  précision/rappel par scénario (INC-5).

---

## 4. Synthèse — table de traçabilité

| Scénario | Primitive(s) | Réf. attaque | Impact co-atc | Défense | Réf. défense |
|---|---|---|---|---|---|
| **V1** Clonage | injection | [2], [3] | cibles indiscernables, confusion, poison IA | D1 + **D2** | [1], [3] / [1], [4] |
| **V2** Trajectoire | injection + modification | [1], [3] | fausse route/phase/alerte | **D1** (+ D3) | [1], [3] |
| **V3** Faux squawk | injection de champ | [2], [4] | fausse urgence, réaction indue | **D2** | [1], [4] |
| **V4** Flooding/DoS | injection massive | [3], [4] | surcharge carte/alertes | D1 + D3 | [1], [3] |
| *(racine commune)* | absence d'auth. | [1], [2] | tout le canal | auth./chiffrement | [2], [4] |

**Lecture d'ensemble.** Toutes les attaques V1–V4 découlent d'une **cause racine unique** :
le canal ADS-B n'authentifie pas ses émetteurs [1], [2]. Les primitives d'injection et de
modification sont expérimentalement établies [3] et pratiquement réalisables à bas coût
[2]. Les défenses applicables sans modifier le protocole ni ajouter de récepteurs — notre
périmètre — sont la **plausibilité cinématique (D1)** et la **cohérence des métadonnées
(D2)** [1], [3], [4] ; la **MLAT/fusion multi-source (D3)** reste la parade la plus forte
mais exige plusieurs récepteurs [1], [2], [3] ; l'**authentification** attaque la racine
mais est difficile à déployer [2], [4]. La **simulation d'impact** [5] cadre notre
évaluation.
