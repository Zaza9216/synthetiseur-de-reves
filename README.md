# 🌙 Synthétiseur de rêves

Application web qui transforme un rêve raconté à voix haute en souvenir illustré :

1. **Enregistrement** du rêve au micro, directement dans le navigateur
2. **Transcription** automatique de la voix en texte
3. **Classification émotionnelle** du rêve (heureux, stressant, neutre…)
4. **Génération d'une image** qui illustre le rêve
5. **Tableau de bord** personnel : historique, filtres par date et par humeur, émotions dominantes

> Projet réalisé dans le cadre du titre RNCP, Bloc 3 : phase de production.

---

## Stack technique

| Couche | Choix |
|---|---|
| Langage | Python 3.12 |
| Framework web | Django 5.2 (LTS) |
| Base de données | PostgreSQL en production, SQLite en local |
| Interface | Bootstrap 5 |
| Gestion des dépendances | [uv](https://docs.astral.sh/uv/) |
| Qualité | ruff (lint PEP 8 + docstrings Google), pytest, pytest-cov |
| CI/CD | GitHub Actions |
| Conteneur | Docker / Docker Compose |
| Serveur applicatif | Gunicorn + WhiteNoise |

---

## Installation locale (venv)

**Prérequis :** macOS ou Linux, Git.

```bash
git clone https://github.com/Zaza9216/synthetiseur-de-reves.git
cd synthetiseur-de-reves
./scripts/install.sh
uv run python manage.py runserver
```

Le script :
- installe `uv` s'il est absent, ainsi que Python 3.12 et les dépendances dans un environnement virtuel `.venv/` ;
- crée le fichier `.env` à partir de `.env.example`, avec une clé secrète générée ;
- crée la base de données locale.

L'application est ensuite disponible sur http://127.0.0.1:8000.

## Installation avec Docker

```bash
cp .env.example .env   # puis renseigner SECRET_KEY et les clés API
docker compose up --build
```

Docker Compose lance l'application et une base PostgreSQL. L'application est disponible sur http://localhost:8000.

---

## Variables d'environnement

| Variable | Rôle | Exemple |
|---|---|---|
| `SECRET_KEY` | Clé secrète Django | *(générée par le script)* |
| `DEBUG` | Mode debug (jamais en production) | `True` |
| `ALLOWED_HOSTS` | Domaines autorisés | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | Origines HTTPS de confiance | `https://mon-app.onrender.com` |
| `DATABASE_URL` | Base de données (vide = SQLite) | `postgres://user:pass@host:5432/db` |
| `LOG_LEVEL` | Niveau de logs | `INFO` |
| `OPENAI_API_KEY` | Clé API OpenAI (transcription, émotion, image) | `sk-...` |
| `TRANSCRIPTION_MODEL` | Modèle de transcription | `gpt-4o-transcribe` |
| `DREAM_PROCESSING_MODE` | `thread` (arrière-plan), `sync` ou `off` | `thread` |
| `DREAM_DAILY_LIMIT` | Rêves maximum par utilisateur et par jour | `10` |
| `IMAGE_MODEL` / `IMAGE_QUALITY` | Modèle et qualité des images | `gpt-image-1-mini` / `medium` |
| `AI_MONTHLY_BUDGET_USD` | Plafond de dépenses IA mensuel ($) | `15` |
| `LOG_FORMAT` | Logs `text` (local) ou `json` (production) | `json` |
| `SLOW_REQUEST_MS` | Seuil d'alerte des requêtes lentes (ms) | `1000` |
| `SENTRY_DSN` | Suivi des erreurs Sentry (facultatif) | `https://…@sentry.io/…` |
| `OPENAI_TIMEOUT` / `OPENAI_MAX_RETRIES` | Délai max par appel (s) / nouvelles tentatives | `60` / `2` |

Le fichier `.env` n'est **jamais** commité.

---

## Qualité et tests

```bash
uv run ruff check .          # lint (PEP 8, imports, docstrings Google)
uv run ruff format .         # formatage automatique
uv run pytest                # tests + rapport de couverture (seuil minimal : 70 %)
```

## Intégration continue

À chaque push et à chaque Pull Request, GitHub Actions :
1. vérifie le lint et le formatage ;
2. lance les tests sur une vraie base PostgreSQL, avec contrôle de couverture ;
3. vérifie la configuration de sécurité de production (`manage.py check --deploy`) ;
4. construit l'image Docker.

---

## Supervision

| Outil | Rôle |
|---|---|
| `GET /health/` | Sonde de santé : `200` si l'application et la base répondent, `503` sinon. Renvoie aussi la version déployée |
| **Page `/supervision/`** (administrateurs) | Rêves traités, taux de succès, durée p50/p95 ; par service d'IA : appels, échecs, latence p50/p95, coût, taux de repli ; budget du mois ; dernières erreurs |
| **Journal `ApiCall`** (admin Django) | Chaque appel d'IA : service, modèle, durée, succès, type d'erreur, coût estimé |
| **Logs JSON** (`LOG_FORMAT=json`) | Une ligne JSON par événement (niveau, module, message, champs utiles) |
| **Requêtes lentes** | Journalisées au-delà de `SLOW_REQUEST_MS`, en-tête `Server-Timing` sur chaque réponse |
| **Sentry** (facultatif) | Erreurs avec trace complète, sans données personnelles (`send_default_pii=False`) |

Pour accéder à la supervision, créez un compte administrateur : `uv run python manage.py createsuperuser`.

## Structure du projet

```
config/      Configuration Django (settings, urls, wsgi)
core/        Pages transverses (accueil, santé)
templates/   Gabarits HTML communs
static/      Fichiers statiques
tests/       Tests automatisés (pytest)
scripts/     Scripts d'installation
```

## Organisation

- Suivi du projet : **GitHub Projects**, en sprints d'une semaine
- Workflow Git : une branche par fonctionnalité → Pull Request → CI verte → merge dans `main`
