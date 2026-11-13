# Journal de bord

Décisions techniques, difficultés rencontrées et solutions apportées, au fil du projet.
Ce journal alimente le rapport technique et la code review.

---

## Sprint 1 : socle technique

### Décision : configuration par variables d'environnement
- **Choix :** `django-environ` et un fichier `.env` jamais commité (`.env.example` sert de modèle).
- **Pourquoi :** aucun secret dans le code ; la même image tourne en local, en CI et en production, seules les variables changent.

### Décision : `uv` pour Python et les dépendances
- **Choix :** `uv` plutôt que `pip` + `venv`.
- **Pourquoi :** il installe Python 3.12 sans droits administrateur (le poste de développement n'en a pas), le fichier `uv.lock` garantit des versions identiques partout, et il est beaucoup plus rapide en CI.

### Décision : pas de Docker sur le poste local
- **Contexte :** Docker Desktop exige un compte administrateur macOS.
- **Solution :** développement en venv (accepté par le sujet). Le `Dockerfile` reste vérifié à chaque push par la CI, qui construit l'image, puis utilisé pour le déploiement.

### 🐞 Bug : test vert en local, rouge en CI
- **Symptôme :** `test_home_page_is_reachable` passait en local et échouait en CI avec `assert 301 == 200`.
- **Diagnostic :** lecture des logs de la CI. La réponse était une redirection 301 vers `https://testserver/`. En local, le `.env` contient `DEBUG=True`, ce qui désactive le bloc de sécurité de production. En CI, il n'y a pas de `.env`, donc `DEBUG=False` et `SECURE_SSL_REDIRECT=True` : toute requête HTTP est redirigée vers HTTPS.
- **Correction :** fixture pytest `autouse` dans `tests/conftest.py`, qui désactive la redirection HTTPS pendant les tests. Le comportement des tests ne dépend plus de l'environnement.
- **Vérification :** tests lancés en local avec et sans `.env`, puis CI verte.
- **Leçon :** les tests ne doivent jamais dépendre de la configuration locale du développeur. Il faut reproduire les conditions de la CI en local avant de pousser.
