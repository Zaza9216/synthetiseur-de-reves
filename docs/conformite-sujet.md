# Conformité au sujet : « Synthétiseur de rêves », dossier de production

Chaque exigence du sujet, avec son état et la preuve correspondante (fichier, test, page ou mesure).

*Application en ligne : https://synthetiseur-de-reves.onrender.com · Dépôt : https://github.com/Zaza9216/synthetiseur-de-reves · Suivi : https://github.com/users/Zaza9216/projects/2*

---

## 3.1 Application fonctionnelle

| Exigence | État | Preuve |
|---|---|---|
| Stack Django + BDD SQL + Bootstrap/Tailwind | ✅ | Django 5.2 LTS, PostgreSQL 16 (production) / SQLite (local), Bootstrap 5.3 |
| Authentification | ✅ | `accounts/` : inscription, connexion, déconnexion ; identifiant insensible à la casse ; blocage anti-force brute |
| Espace utilisateur avec historique de rêves | ✅ | `/reves/` : historique paginé, cloisonné par utilisateur (404 sinon) ; `tests/test_dreams_history.py` |
| Enregistrement audio | ✅ | `static/js/recorder.js` (MediaRecorder, onde de la voix) + import de fichier ; signature du fichier vérifiée côté serveur ; test navigateur avec micro simulé |
| Transcription (Whisper/OpenAI ou équivalent) | ✅ | `dreams/ai/transcription.py` : `gpt-4o-transcribe`, choisi après comparaison de 3 modèles (journal de bord) |
| Classification émotionnelle (NLTK, Hugging Face, etc.) | ✅ | `dreams/ai/emotion.py` : `gpt-4o-mini` en sortie structurée + lexique local de secours ; 7/7 sur le jeu d'évaluation ; Hugging Face écarté (API devenue payante, HTTP 402) |
| Génération d'image (Stable Diffusion / DALL·E) | ✅ | `dreams/ai/image.py` : `gpt-image-1-mini`, WebP ; ambiance visuelle selon l'émotion |
| Micro-vidéo + ambiance sonore (**bonus**) | ✅ | « Revivre mon rêve » : image animée (effet Ken Burns) + récit en sous-titres + ambiance synthétisée par émotion (Web Audio API), `static/js/ambience.js` |
| Tableau de bord : filtres date et humeur | ✅ | `/reves/?start=…&end=…&emotion=…` (+ recherche texte) ; `tests/test_dashboard.py`, test navigateur |
| Tableau de bord : fréquences, émotions dominantes | ✅ | Fréquence par semaine, émotion dominante, répartition, évolution par semaine ou par mois (`dreams/stats.py`) |
| CI/CD : tests unitaires, linting, build, déploiement automatisé | ✅ | `.github/workflows/ci.yml` : ruff → pytest (PostgreSQL) → navigateurs (Chromium + WebKit) → build Docker → déploiement Render → vérification de la version en ligne |
| README complet + script d'installation (Docker/venv + .env) | ✅ | `README.md`, `scripts/install.sh` (venv), `Dockerfile`, `docker-compose.yml`, `.env.example` |

## 4. Contraintes techniques

| Contrainte | État | Preuve |
|---|---|---|
| Python (Django, FastAPI ou Flask) | ✅ | Python 3.12, Django 5.2 |
| Déploiement Heroku / Render / Docker Compose | ✅ | **Render** (`render.yaml`, région Francfort) et Docker Compose local |
| APIs : budget total ≤ 20 € | ✅ | ≈ 0,012 $ par rêve mesuré ; **plafond automatique de 15 $ par mois** (`dreams/ai/budget.py`), alerte à 80 % ; quota de 10 rêves par jour et par utilisateur ; crédit OpenAI de 10 $ sans recharge automatique |
| Couverture de tests ≥ 70 % des fonctionnalités critiques | ✅ | **99 %** (seuil de 70 % bloquant en CI) ; 299 tests unitaires et d'intégration + 14 tests navigateurs |
| PEP 8 | ✅ | `ruff` (règles E, W, F, I, UP, B, DJ), bloquant en CI |
| Docstrings Google | ✅ | `ruff` (règles D, convention `google`), bloquant en CI |
| Branches Git avec PR | ✅ | Une branche par issue, **22 Pull Requests**, aucun commit direct sur `main` après l’initialisation (vérifié) |

## 3.2 Rapport technique (contenu à couvrir)

| Attendu | Matériau disponible |
|---|---|
| Architecture finale mise à jour | `README.md` (stack, structure), `render.yaml`, journal de bord (décisions) |
| Gestion des appels API / quota / erreurs | `dreams/ai/` (timeout, nouvelles tentatives, traduction des erreurs, journal `ApiCall`, budget), PR #25 |
| Stratégie de tests | Unitaires, intégration, navigateurs, charge ; leçons des bugs #23 et #46 |
| Monitoring, logs, métriques clefs | `/supervision/`, logs JSON, `/health/`, UptimeRobot, Sentry (facultatif) |
| Difficultés techniques et solutions | `docs/journal-de-bord.md` (32 entrées : 🐞 bugs, 🧱 difficultés, 📊 mesures) |
| Répartition du travail + accès GitHub et suivi | Travail individuel ; dépôt public ; GitHub Projects (4 sprints, issues avec critères d'acceptation) |

## 3.4 Code review live

| Attendu | Ticket préparé |
|---|---|
| Ticket ou feature résolu | **Bug #23** : bouton « Supprimer » inopérant (PR #24), puis sa **suite** (correctif incomplet détecté par les tests navigateurs, PR #45) |
| Comparaison avant/après, méthode de debug/refactor | Commit « test qui reproduit le bug » puis commit « correctif » (TDD) ; diagnostic dans le journal de bord |
| Explication des choix (perf, lisibilité, testabilité) | Test de l'invariant (« une seule fenêtre ») plutôt que du symptôme ; tests navigateurs ajoutés en conséquence |

*Alternatives possibles : bug #46 (connexion sur iPhone), bug #35 (chargement lent mesuré avant d'être corrigé), test de charge (goulot identifié et corrigé).*

## 6. Grille d'évaluation : où regarder

| Axe | Éléments à montrer |
|---|---|
| Fonctionnalités implémentées | Démo en ligne : inscription → enregistrement → résultat → tableau de bord → « Revivre mon rêve » |
| Qualité du code | ruff en CI, docstrings Google, séparation `dreams/ai/` / `pipeline.py` / vues, typage |
| Intégration des outils IA | Timeouts, nouvelles tentatives, repli, budget, journal `ApiCall`, benchmarks de modèles |
| Tests et validation | 99 % de couverture, tests navigateurs (3 profils), test de charge (`docs/test-de-charge.md`) |
| CI/CD & déploiement | Pipeline en 6 étapes, `render.yaml`, smoke test de la version en ligne, logs JSON |
| Performance & optimisation | Test de charge (56 s → 12 s), diagnostic du chargement mobile (51 s → 0,1 s), WebP, agrégations SQL |
| Documentation & rapport | README, journal de bord, conformité, captures, rapport PDF |
| Post-mortem | Leçons tirées du journal (écarts local/CI, tests du symptôme vs de l'invariant, mesurer avant d'optimiser) |
| Code review | Bug #23 et sa suite |

## Au-delà du sujet

- **Sécurité** : CSP sans script en ligne, Permissions-Policy, blocage anti-force brute (avec lecture correcte de l'IP derrière le proxy), fichiers privés servis après contrôle d'accès, base non exposée sur Internet, HSTS, audit des dépendances (`pip-audit` : aucune vulnérabilité connue), aucun secret dans l'historique Git.
- **RGPD** : export ZIP, suppression du compte, page de confidentialité, hébergement dans l'UE, journaux sans contenu des rêves.
- **Accessibilité** : contrastes WCAG AA vérifiés, libellés pour lecteurs d'écran, focus visible, mouvements réduits respectés.
- **Mobile** : PWA installable, thème allégé sur écran tactile, identifiant insensible aux majuscules automatiques.
