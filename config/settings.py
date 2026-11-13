"""Configuration Django du projet « Synthétiseur de rêves ».

Toutes les valeurs sensibles ou dépendantes de l'environnement (clé secrète,
mode debug, base de données, clés API) sont lues depuis les variables
d'environnement ou un fichier ``.env`` local, jamais écrites en dur.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    LOG_LEVEL=(str, "INFO"),
)
environ.Env.read_env(BASE_DIR / ".env")

# --- Sécurité -----------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # la sonde de l'hébergeur appelle en HTTP
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
    # Préchargement HSTS = engagement quasi irréversible : volontairement non activé.
    SILENCED_SYSTEM_CHECKS = ["security.W021"]

# --- Applications --------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Applications du projet
    "core",
    "accounts",
    "dreams",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de données -------------------------------------------------------------
# SQLite en local par défaut ; PostgreSQL en production via DATABASE_URL.
DATABASE_URL = env("DATABASE_URL", default="") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {"default": env.db_url_config(DATABASE_URL)}
DATABASES["default"]["CONN_MAX_AGE"] = 60

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentification ----------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dreams:list"
LOGOUT_REDIRECT_URL = "core:home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation ------------------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# --- Fichiers statiques et médias -------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Rêves ------------------------------------------------------------------------
DREAM_AUDIO_MAX_MB = env.int("DREAM_AUDIO_MAX_MB", default=10)
DREAM_AUDIO_MAX_SECONDS = env.int("DREAM_AUDIO_MAX_SECONDS", default=300)
# Nombre maximal de rêves par utilisateur et par jour (maîtrise du budget API).
DREAM_DAILY_LIMIT = env.int("DREAM_DAILY_LIMIT", default=10)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# --- Services d'IA -------------------------------------------------------------------
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_TIMEOUT = env.float("OPENAI_TIMEOUT", default=60.0)  # secondes, par tentative
OPENAI_MAX_RETRIES = env.int("OPENAI_MAX_RETRIES", default=2)
TRANSCRIPTION_MODEL = env("TRANSCRIPTION_MODEL", default="gpt-4o-transcribe")
EMOTION_MODEL = env("EMOTION_MODEL", default="gpt-4o-mini")

# Traitement des rêves : "thread" (arrière-plan, par défaut), "sync" (immédiat), "off".
DREAM_PROCESSING_MODE = env("DREAM_PROCESSING_MODE", default="thread")
DREAM_PROCESSING_WORKERS = env.int("DREAM_PROCESSING_WORKERS", default=2)
DREAM_STALLED_MINUTES = env.int("DREAM_STALLED_MINUTES", default=10)

# --- Logs ------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL")},
}
