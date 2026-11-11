# ADR-0005 — Attaque phare : clonage d'aéronefs

- **Statut :** Accepté
- **Date :** 2026-11-08
- **Décideurs :** Auteur(s)

## Contexte

On vise à explorer au moins deux vulnérabilités. Il faut une attaque centrale à fort impact démonstratif, rattachée à la littérature.

## Décision

Retenir comme attaque phare le **clonage d'aéronefs** : pour chaque avion réel du flux de référence, émettre **plusieurs copies** portant le même indicatif et le même type, à des positions, caps et altitudes décalés, avec des adresses ICAO distinctes. Objectif : rendre **le vrai indiscernable de ses leurres**. Attaques secondaires : spoofing de trajectoire (V2), faux squawk d'urgence (V3), saturation/DoS (V4).

## Alternatives envisagées

- **Cibles fantômes aléatoires** — écarté comme pièce maîtresse : visuellement suspectes, moins fortes que des clones calqués sur du trafic réel.
- **Réutiliser le même hex ICAO pour les clones** — conservé seulement comme sous-cas : une adresse à deux positions est un signal de détection (« téléportation »), donc moins « confusant » mais utile pour la défense D2.

## Conséquences

- Positives : démonstration marquante ; couvre V1–V2 d'un coup (clones à trajectoires divergentes) ; motive directement la défense.
- Négatives : exige un flux de référence réaliste à cloner (base `.db` rejouée ou OpenSky).
- Suivi : définir le facteur de clonage N et le bruit de position comme paramètres d'expérimentation.
