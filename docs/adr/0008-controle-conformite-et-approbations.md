# ADR-0008 — Contrôle de conformité et portes d'approbation

- **Statut :** Accepté
- **Date :** 2026-11-09
- **Décideurs :** Auteur(s)

## Contexte

Le projet s'appuie sur plusieurs agents (chercheur, architecte, dev-attaque, dev-défense, rédacteur). Sans contrôle, un agent pourrait déborder de son mandat, modifier le cœur de co-atc, publier en ligne, ou prendre une décision structurante sans trace. On veut garantir que les agents font **uniquement ce qui est prévu** et n'agissent pas sans contrôle ni approbation sur les éléments importants.

## Décision

Introduire un agent **Conformité & Sécurité** (`.claude/agents/adsb-conformite-securite.md`), en **lecture seule**, chargé d'auditer le travail des autres agents contre les ADR et un jeu de **contraintes dures** et de **portes d'approbation**.

Contraintes dures (tout manquement est bloquant) : aucune émission RF réelle ; aucune publication en ligne sans accord explicite ; cœur de co-atc non modifié ; aucune référence inventée ; aucun secret commité ou exfiltré ; portée vase clos.

Portes d'approbation (nécessitent un feu vert humain avant exécution) : actions irréversibles ou tournées vers l'extérieur, changement de config de co-atc, nouvelle dépendance/appel réseau, dérive de périmètre, décision structurante sans ADR.

L'agent **ne corrige rien lui-même** : il rend un verdict `CONFORME` / `CONFORME SOUS RÉSERVE` / `BLOQUANT` avec preuves (`fichier:ligne`).

## Alternatives envisagées

- **Confiance implicite dans chaque agent** — écarté : pas de garantie ni de traçabilité.
- **Un seul agent cumulant dev et contrôle** — écarté : juge et partie ; l'indépendance du contrôleur est nécessaire.

## Conséquences

- Positives : garde-fou traçable, respect du cadre éthique et du périmètre, décisions importantes validées par un humain.
- Négatives : étape de revue supplémentaire ; l'agent dépend de la qualité des ADR pour juger (d'où l'importance de les tenir à jour).
- Suivi : lancer cet agent après chaque livraison d'un agent dev et avant toute action sensible.
