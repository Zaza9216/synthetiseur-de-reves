"""Configuration et fixtures communes à tous les tests."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from pytest_django.fixtures import Settings

from dreams.models import Dream

User = get_user_model()
STRONG_PASSWORD = "Reve-Lucide-2026!"


@pytest.fixture(autouse=True)
def _disable_https_redirect(settings: Settings) -> None:
    """Désactive la redirection HTTPS pendant les tests.

    Le client de test Django parle en HTTP. Sans cette fixture, les tests
    se comportent différemment selon l'environnement : en local, ``DEBUG=True``
    (lu depuis ``.env``) désactive la redirection, alors qu'en CI, sans ``.env``,
    la configuration de production redirige toutes les pages en 301 vers HTTPS.

    Args:
        settings: Fixture pytest-django permettant de surcharger les réglages.
    """
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture(autouse=True)
def _simple_static_storage(settings: Settings) -> None:
    """Utilise un stockage statique simple pendant les tests.

    En production, WhiteNoise sert les fichiers statiques via un manifeste
    (noms de fichiers avec empreinte, pour le cache navigateur) généré par
    ``collectstatic``. Ce manifeste n'existe pas pendant les tests : sans
    cette fixture, toute page utilisant ``{% static %}`` lève une erreur.

    Args:
        settings: Fixture pytest-django permettant de surcharger les réglages.
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(autouse=True)
def _temporary_media_root(settings: Settings, tmp_path: Path) -> None:
    """Écrit les fichiers envoyés pendant les tests dans un dossier temporaire.

    Args:
        settings: Fixture pytest-django permettant de surcharger les réglages.
        tmp_path: Dossier temporaire propre à chaque test.
    """
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def user(db: None) -> Any:
    """Utilisateur standard."""
    return User.objects.create_user("bob", "bob@example.com", STRONG_PASSWORD)


@pytest.fixture
def other_user(db: None) -> Any:
    """Second utilisateur, pour vérifier le cloisonnement des données."""
    return User.objects.create_user("eve", "eve@example.com", STRONG_PASSWORD)


@pytest.fixture
def make_dream(db: None) -> Callable[..., Dream]:
    """Fabrique de rêves avec des valeurs par défaut réalistes.

    Returns:
        Une fonction ``make_dream(user, **champs)`` qui crée et retourne un rêve.
    """

    def _make(user: Any, **fields: Any) -> Dream:
        defaults: dict[str, Any] = {
            "transcription": "Je volais au-dessus d'une ville de verre sous un ciel violet.",
            "emotion": "heureux",
            "emotion_score": 0.87,
            "status": "termine",
        }
        defaults.update(fields)
        return Dream.objects.create(user=user, **defaults)

    return _make


def fake_audio(name: str = "reve.webm") -> SimpleUploadedFile:
    """Construit un faux fichier audio pour les tests."""
    return SimpleUploadedFile(name, b"fake-audio-bytes", content_type="audio/webm")
