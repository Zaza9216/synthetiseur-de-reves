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

### Décision : modèle utilisateur personnalisé dès le départ
- **Choix :** `accounts.User` (hérite d'`AbstractUser`) avec un email unique et obligatoire.
- **Pourquoi :** Django recommande de le faire **avant la première migration**. Changer de modèle utilisateur une fois la base en production impose des migrations lourdes et risquées.

### Décision : cloisonnement des données par utilisateur
- **Choix :** toutes les vues des rêves héritent d'un mixin `UserDreamsMixin`, qui filtre le queryset sur `request.user`.
- **Pourquoi :** un rêve est une donnée intime. Si un utilisateur demande le rêve d'un autre, il reçoit une **404** et non une 403 : on ne révèle même pas que le rêve existe. Le filtre est centralisé dans un seul mixin, donc impossible à oublier dans une nouvelle vue.

### Décision : noms de fichiers anonymes
- **Choix :** les fichiers audio et les images sont renommés en `dreams/<type>/<année>/<mois>/<uuid>.<ext>`.
- **Pourquoi :** le nom d'origine peut contenir des données personnelles (« Rêve de Bob.mp3 »). L'UUID empêche aussi de deviner l'adresse des fichiers des autres utilisateurs.

### Décision : statut de traitement sur le rêve
- **Choix :** un champ `status` suit chaque étape (en attente → transcription → analyse → génération → terminé / échec), complété par un `error_message`.
- **Pourquoi :** les appels aux API d'IA prennent plusieurs secondes et peuvent échouer. L'interface doit toujours pouvoir dire où en est le traitement, ce qui prépare le traitement en arrière-plan du Sprint 2.

### Décision : supprimer les fichiers avec un signal `post_delete`
- **Constat :** Django supprime la ligne en base, mais **jamais les fichiers** liés (`FileField`). Les enregistrements vocaux, qui sont des données personnelles, resteraient sur le disque.
- **Choix :** un signal `post_delete` sur `Dream` plutôt qu'une surcharge de `Dream.delete()`.
- **Pourquoi :** `delete()` n'est **pas appelée** lors des suppressions en masse (`queryset.delete()`) ni lors de la cascade quand un compte est supprimé. Le signal, lui, est émis dans tous ces cas. Le test `test_deleting_user_account_removes_dream_files` le vérifie.
- **Robustesse :** une erreur de stockage est journalisée, mais ne bloque pas la suppression.
