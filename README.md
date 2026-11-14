# 🌙 Synthétiseur de rêves

[![CI](https://github.com/Zaza9216/synthetiseur-de-reves/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Zaza9216/synthetiseur-de-reves/actions/workflows/ci.yml)

**🔗 Application en ligne : https://synthetiseur-de-reves.onrender.com**

Application web qui transforme un rêve raconté à voix haute en souvenir illustré :

1. **Enregistrement** du rêve au micro (avec visualisation de la voix) ou import d'un fichier audio
2. **Transcription** automatique de la voix en texte (`gpt-4o-transcribe`)
3. **Classification émotionnelle** du rêve parmi 6 émotions (`gpt-4o-mini`, lexique de secours)
4. **Génération d'une image** qui illustre le rêve (`gpt-image-1-mini`)
5. **Tableau de bord** personnel : filtres par date, humeur et texte, fréquence, émotion dominante, évolution
6. **« Revivre mon rêve »** *(bonus du sujet)* : micro-vidéo (image animée et récit) et ambiance sonore générée selon l'émotion
7. **Espace « Mes données »** : export complet et suppression du compte (RGPD)
8. **Application installable** sur l'écran d'accueil du téléphone (PWA)

📸 Captures : [`docs/captures/`](docs/captures/) · 📓 Décisions et difficultés : [`docs/journal-de-bord.md`](docs/journal-de-bord.md) · 📊 Test de charge : [`docs/test-de-charge.md`](docs/test-de-charge.md) · ✅ Conformité au sujet : [`docs/conformite-sujet.md`](docs/conformite-sujet.md)

> Projet réalisé dans le cadre du titre RNCP, Bloc 3 : phase de production.

---

## Stack technique

| Couche | Choix |
|---|---|
| Langage | Python 3.12 |
| Framework web | Django 5.2 (LTS) |
| Base de données | PostgreSQL en production, SQLite en local |
| Interface | Bootstrap 5, thème « Nuit étoilée » (CSS), Chart.js, Web Audio API |
| IA | OpenAI : transcription, émotion (sortie structurée), image |
| Gestion des dépendances | [uv](https://docs.astral.sh/uv/) |
| Qualité | ruff (lint PEP 8 + docstrings Google), pytest, pytest-cov, Playwright (navigateurs), Locust (charge) |
| Sécurité | django-axes (force brute), CSP, Permissions-Policy, HSTS |
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
uv run pytest -m e2e --no-cov # tests de bout en bout dans de vrais navigateurs
                             # (une fois : uv run playwright install chromium webkit ;
                             #  sans DEBUG=True dans .env, ajouter SECURE_SSL_REDIRECT=False
                             #  SECURE_HSTS_SECONDS=0 SECURE_COOKIES=False)
```

## Déploiement (Render)

L'infrastructure est décrite dans [`render.yaml`](render.yaml) : un service web Docker et une base PostgreSQL, **hébergés à Francfort** (Union européenne, RGPD). La base n'est **pas accessible depuis Internet** (réseau privé Render uniquement).

### Première mise en place
1. Sur [render.com](https://render.com) : **New → Blueprint**, choisir ce dépôt, puis renseigner les secrets demandés (`OPENAI_API_KEY`, `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`).
2. Dans le service web : **Settings → Deploy Hook**, copier l'URL.
3. Dans GitHub : secret `RENDER_DEPLOY_HOOK_URL` (l'URL du hook) et variable `APP_URL` (l'adresse publique, par exemple `https://synthetiseur-de-reves.onrender.com`).

### Déploiements suivants : automatiques
À chaque merge sur `main`, la CI lance lint, tests et build Docker. **Si tout est vert**, elle déclenche le déploiement, puis vérifie que la nouvelle version répond sur `/health/` (comparaison du commit).

### Particularités de l'offre gratuite
| Limite | Conséquence | Parade |
|---|---|---|
| Disque éphémère | Les fichiers locaux sont effacés à chaque redémarrage | Audio et images stockés **dans PostgreSQL** (`MEDIA_STORAGE=database`) |
| Mise en veille après 15 min d'inactivité | Premier chargement d'environ 50 s | **UptimeRobot** appelle `/health/` toutes les 5 min (et tâche GitHub `keep-warm.yml` en secours) |
| Base gratuite valable 30 jours | Elle doit être recréée ensuite | À recréer avant la soutenance si besoin |
| Pas de terminal sur le serveur | Impossible de lancer `createsuperuser` | Commande `ensure_admin` au démarrage (variables `ADMIN_*`) |

## Intégration continue

À chaque push et à chaque Pull Request, GitHub Actions :
1. vérifie le lint et le formatage ;
2. lance les tests sur une vraie base PostgreSQL, avec contrôle de couverture ;
3. rejoue les parcours utilisateurs dans de vrais navigateurs (Chromium pour ordinateur et Android, WebKit pour iPhone) ;
4. vérifie la configuration de sécurité de production (`manage.py check --deploy`) ;
5. construit l'image Docker ;
6. **sur `main` uniquement**, déploie sur Render et vérifie la mise en ligne de la nouvelle version.

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
| **UptimeRobot** (externe) | Disponibilité vue de l'extérieur toutes les 5 min, alerte par email en cas de panne |

Pour accéder à la supervision, créez un compte administrateur : `uv run python manage.py createsuperuser`.

## Structure du projet

```
config/           Configuration Django (settings, urls, wsgi)
accounts/         Comptes : inscription, connexion, « Mes données » (export, suppression)
dreams/           Rêves : modèles, vues, pipeline de traitement, tableau de bord
dreams/ai/        Services d'IA : transcription, émotion, image, budget, journal des appels
core/             Transverse : accueil, santé, supervision, sécurité, PWA, stockage en base
templates/        Gabarits HTML communs
static/           CSS du thème, JavaScript (enregistreur, suivi, graphiques, ambiance), icônes
tests/            Tests unitaires et d'intégration (pytest)
tests/e2e/        Tests de bout en bout dans de vrais navigateurs (Playwright)
loadtests/        Test de charge (Locust)
scripts/          Installation, démarrage en production, captures d'écran
docs/             Journal de bord, test de charge, conformité, captures
```

## Organisation

- Suivi du projet : **[GitHub Projects](https://github.com/users/Zaza9216/projects/2)**, en 4 sprints
- Workflow Git : une branche par fonctionnalité → Pull Request → CI verte → merge dans `main`
