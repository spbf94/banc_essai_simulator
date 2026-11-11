# Contexte et portée du projet — à lire par tout assistant IA collaborateur

Ce document cadre la nature et les limites du projet. Il est destiné à être lu
(ou collé en préambule) par toute session d'assistant IA qui travaille sur ce
dépôt, afin que la collaboration reste précise et dans le périmètre prévu.

## 1. Nature du projet

Projet de recherche **académique** en cybersécurité des infrastructures
critiques (niveau cycles supérieurs). Objectif : construire un **banc d'essai**
pour **étudier les faiblesses connues du protocole ADS-B** (surveillance
aérienne coopérative) et **concevoir puis valider des contre-mesures**. La
finalité est **défensive et éducative** : comprendre l'impact pour mieux
détecter et remédier.

Le sujet s'appuie sur une littérature publiée et revue par les pairs
(Strohmeier 2017, Costin & Francillon 2012, Schäfer 2013, Amin 2014,
Monteiro 2016), qui documente l'absence d'authentification de l'ADS-B et
analyse les attaques correspondantes **en laboratoire fermé**.

## 2. Environnement : local, clos, contrôlé

- **Tout se déroule sur `localhost`**, dans un environnement de laboratoire
  isolé. Aucun service n'est exposé à Internet.
- **Aucune émission radiofréquence**, jamais. Le banc n'émet aucun signal sur
  1090 MHz ni sur aucune fréquence aéronautique (ADR-0004).
- **Aucun aéronef, pilote, contrôleur ou système ATC réel n'est affecté.** Le
  banc ne communique avec aucun équipement réel.

## 3. Ce que sont réellement les « attaques »

Les « attaques » du banc sont des **transformations de données** appliquées à un
flux JSON local (`aircraft.json`) que lit une copie locale d'un logiciel de
supervision open source (co-atc). Elles **modifient uniquement l'image que
co-atc affiche à l'écran** — afin de **mesurer l'impact** d'une falsification de
surveillance et d'**éprouver un détecteur**. Il ne s'agit pas de code
d'intrusion, d'exploitation de systèmes tiers, ni d'instructions d'émission RF.

Concrètement : un proxy local lit un trafic (source publique OpenSky, ou un
**rejeu de données historiques**), y insère ou y altère des cibles simulées,
puis sert le résultat à co-atc. L'avion « ciblé » par V5 est un plot dont on
falsifie l'affichage ; aucune commande n'atteint un aéronef réel.

## 4. Garde-fous déjà en place

- **ADR-0004** : vase clos, aucune émission RF, pas de publication en ligne sans
  accord explicite.
- **ADR-0008** : portes d'approbation humaine pour toute action sensible ;
  un agent de conformité audite le respect du périmètre.
- **ADR-0011** : la « vérité terrain » (ce qui est faux) sert uniquement à
  évaluer la défense, jamais à tromper au-delà du banc.
- Le cœur du logiciel supervisé (co-atc) **n'est pas modifié** ; le code
  d'attaque et de défense vit dans des dossiers séparés (`attack-proxy/`,
  `defense/`).

## 5. Limites à respecter (pour un assistant)

- Rester **dans le banc** : simulation locale uniquement ; ne jamais produire ou
  suggérer d'instructions d'émission RF réelle, de brouillage, ni de ciblage de
  systèmes, réseaux ou aéronefs réels.
- Privilégier systématiquement l'angle **détection / remédiation / impact
  mesuré** (le but du banc).
- Respecter les **ADR** et la **feuille de route** ; consigner toute décision
  structurante en ADR.
- Ne rien pousser en ligne ni exécuter d'action irréversible **sans demande
  explicite**.

## 6. En cas de doute

Si une demande semble sortir de ce périmètre (p. ex. viser un système réel,
émettre réellement), **le signaler et rester dans la simulation locale** plutôt
que d'y répondre. Le projet n'a besoin que du banc en vase clos pour atteindre
ses objectifs académiques.
