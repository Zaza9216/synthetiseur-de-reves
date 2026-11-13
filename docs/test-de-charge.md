# Test de charge : résultats et analyse

*Date : 13 novembre 2026 · Outil : Locust 2 · Scénario : [`loadtests/locustfile.py`](../loadtests/locustfile.py)*

## Objectif
Déterminer combien de rêves l'application peut traiter simultanément, repérer le goulot d'étranglement et ajuster la configuration de production.

## Conditions
| Élément | Valeur |
|---|---|
| Serveur | Gunicorn `gthread`, **2 processus × 4 fils**, `DEBUG=False`, logs JSON |
| Base de données | **PostgreSQL 16** (instance locale, comme en production) |
| Stockage des fichiers | En base (`MEDIA_STORAGE=database`), comme en production |
| Services d'IA | **Simulés** (`AI_BACKEND=fake`) avec les latences mesurées en réel : 1,2 s + 0,9 s + 10,2 s |
| Machine | MacBook (Apple Silicon), client et serveur sur la même machine |
| Paliers | 10, 25, 50 puis 150 utilisateurs, arrivée de 5 à 10 par seconde, 2 à 2,5 min chacun |

> **Pourquoi des IA simulées ?** On mesure la capacité de **notre** application, pas celle d'OpenAI, et sans dépenser de budget. Les latences simulées sont celles mesurées sur l'API réelle (voir le journal de bord).
>
> **Pourquoi pas sur Render ?** L'offre gratuite (0,1 processeur partagé, mise en veille) fausserait les mesures, et une charge artificielle pourrait être interprétée comme une attaque.

## Résultats

### 1. Configuration initiale : 2 fils de traitement par processus (4 rêves traités en parallèle)
| Utilisateurs | Requêtes | Erreurs | Tableau de bord p50 / p95 | Envoi d'un rêve p95 | **Rêve complet p50 / p95** | Rêves traités /s |
|---|---|---|---|---|---|---|
| 10 | 380 | 1* | 18 / 24 ms | 23 ms | **14 / 22 s** | 0,15 |
| 25 | 1 009 | 0 | 18 / 24 ms | 21 ms | **26 / 38 s** | 0,25 |
| 50 | 2 819 | 0 | 16 / 23 ms | 23 ms | **56 / 85 s** | 0,27 |

\* Erreur de connexion côté client, corrigée ensuite (voir « Défaut révélé »).

**Constat :** les pages restent très rapides (p95 < 25 ms) quelle que soit la charge, mais le **délai pour obtenir un rêve complet explose** : il est multiplié par 4 entre 10 et 50 utilisateurs. Le débit plafonne à environ 0,27 rêve par seconde, très proche de la capacité théorique de 4 traitements ÷ 12,3 s = 0,33 rêve par seconde. **Le goulot d'étranglement est la file de traitement des rêves**, pas le serveur web ni la base de données.

### 2. Hypothèse : le traitement attend l'IA (entrées/sorties), il n'utilise presque pas le processeur
Si c'est vrai, augmenter le nombre de fils de traitement doit augmenter le débit sans saturer la machine.

| Utilisateurs | Fils de traitement | Erreurs | Tableau de bord p95 | **Rêve complet p50 / p95** | Rêves traités /s | Mémoire |
|---|---|---|---|---|---|---|
| 50 | 2 par processus | 0 | 23 ms | 56 / 85 s | 0,27 | — |
| 50 | **8 par processus** | **0** | 21 ms | **12 / 16 s** | **0,70** | 192 Mo |
| 150 | 8 par processus | **0** / 7 910 requêtes | 19 ms | 38 / 67 s | **1,16** | 194 Mo |

**Hypothèse confirmée :** à 50 utilisateurs, le délai d'un rêve complet passe de **56 s à 12 s** (p50), revenant au temps de traitement nominal, et la mémoire reste stable (≈ 190 Mo, sous les 512 Mo de l'offre gratuite Render).

### 3. Limite mesurée
À **150 utilisateurs simultanés**, l'application ne produit **aucune erreur** et les pages restent instantanées (p95 de 19 ms). Seul le délai d'obtention d'un rêve s'allonge (p50 de 38 s). La capacité de traitement est d'environ **1,2 rêve par seconde, soit environ 4 300 rêves par heure**, pour 16 traitements en parallèle. Au-delà, les rêves **attendent leur tour sans jamais échouer**, et la page de suivi informe l'utilisateur.

Avec le quota de 10 rêves par jour et par utilisateur, cette capacité couvre largement des milliers d'utilisateurs actifs. En pratique, **le budget d'IA est la vraie limite** : 1,2 rêve par seconde × 0,012 $ ≈ 50 $ par heure, d'où le plafond mensuel de 15 $, qui bloquerait bien avant la saturation technique.

## Défaut révélé par le test : « Connection reset by peer »
- **Symptôme :** quelques erreurs `ConnectionResetError` côté client, sans aucune erreur côté serveur (les journaux de Gunicorn montrent uniquement des réponses 200 et 201).
- **Cause :** Gunicorn ferme par défaut une connexion inactive au bout de **2 s**. La page de suivi interroge le serveur toutes les **2 s**, et les utilisateurs marquent des pauses de 2 à 6 s. Le client réutilise donc parfois une connexion que le serveur ferme au même instant.
- **Correction :** `--keep-alive 75` dans `scripts/start.sh`, plus long que les pauses des utilisateurs et que le délai du proxy de l'hébergeur.
- **Vérification :** 50 utilisateurs, **0 erreur sur 2 210 requêtes** après correction.

## Décisions prises
| Décision | Justification |
|---|---|
| `--keep-alive 75` (Gunicorn) | Supprime les erreurs « Connection reset » révélées par le test |
| `DREAM_PROCESSING_WORKERS=4` en production (8 traitements simultanés) | Débit multiplié par environ 2,5 d'après les mesures. Pas 8 par processus en production : les limites de débit d'OpenAI pour un compte récent (images par minute) provoqueraient des erreurs 429 et des nouvelles tentatives, sans gain réel |
| Conserver le traitement en fils d'exécution (pas de Celery) | Suffisant pour la charge visée. La fonction `enqueue_dream` isole ce choix si le besoin évolue |

## Limites de ce test et pistes
- Client et serveur partageaient la même machine : les temps des pages sont **optimistes** par rapport à Render (0,1 processeur). Le goulot d'étranglement identifié, la file de traitement, reste le même.
- Les fils de traitement vivent dans les processus web : un redémarrage interrompt les traitements en cours. La parade existe déjà (détection des rêves bloqués et bouton « Relancer »). Au-delà de quelques milliers de rêves par jour, une **file de tâches dédiée** (Celery ou RQ avec Redis) découplerait le traitement du serveur web et permettrait d'ajouter des machines de traitement indépendamment.
- Les limites de débit des API d'IA ne sont pas simulées. Il faudrait un test complémentaire sur l'API réelle, à faible volume pour préserver le budget.

## Fichiers
- Statistiques brutes : `docs/charge/*_stats.csv`
- Rapports Locust interactifs : `docs/charge/rapport-50-utilisateurs-2-fils.html` et `docs/charge/rapport-50-utilisateurs-8-fils.html`
