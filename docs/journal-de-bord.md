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

---

## Sprint 2 : pipeline IA

### 🧱 Difficulté : l'inférence gratuite Hugging Face n'est plus disponible
- **Constat :** les appels aux modèles d'émotion sur Hugging Face (`MilaNLProc/xlm-emo-t`, `j-hartmann/emotion-english-distilroberta-base`, modèles zero-shot multilingues) renvoient **HTTP 402**. Les « Inference Providers » demandent des crédits prépayés ou un abonnement PRO.
- **Alternatives étudiées :**
  - faire tourner le modèle localement avec `transformers` : environ 1 Go de dépendances (PyTorch) et une RAM incompatible avec un hébergement gratuit (512 Mo) ;
  - acheter des crédits Hugging Face : un deuxième fournisseur payant à gérer ;
  - **`gpt-4o-mini` d'OpenAI**, déjà utilisé pour la transcription : il comprend nativement le français et coûte environ 0,0001 $ par rêve.
- **Décision :** classification par `gpt-4o-mini`, avec en secours un **classifieur lexical local** (mots-clés français) pour que l'application réponde même si l'API est indisponible.

### Décision : valider l'audio par sa signature, pas par son nom
- **Choix :** on lit les premiers octets du fichier envoyé (signature WebM, Ogg, WAV, FLAC, MP4, MP3), en plus de vérifier l'extension, la taille (10 Mo) et la durée (5 min).
- **Pourquoi :** le nom et le type MIME sont fournis par le navigateur, donc falsifiables. Un fichier texte ou un exécutable renommé en `.mp3` est refusé **avant** d'être stocké ou envoyé (et facturé) à l'API.

### Décision : quota de 10 rêves par jour et par utilisateur
- **Pourquoi :** c'est l'hypothèse d'usage retenue en pré-production (10 rêves par jour), et chaque rêve déclenche des appels payants. Le quota protège le budget de 20 € contre un usage abusif ou un script. La valeur se règle avec la variable `DREAM_DAILY_LIMIT`.

### 🐞 Bug : « Missing staticfiles manifest entry » dans les tests
- **Symptôme :** dès l'ajout du premier fichier JavaScript (`recorder.js`), les tests de la page d'enregistrement levaient `ValueError: Missing staticfiles manifest entry for 'js/recorder.js'`.
- **Diagnostic :** en production, WhiteNoise sert les statiques via un **manifeste** (noms avec empreinte, pour le cache) généré par `collectstatic`. Les tests tournent avec `DEBUG=False`, donc avec ce stockage, mais sans avoir lancé `collectstatic`.
- **Correction :** fixture `autouse` qui utilise le stockage statique simple pendant les tests. La production garde le manifeste, et le build Docker de la CI vérifie que `collectstatic` fonctionne.
