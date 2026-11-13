"""Configuration commune à tous les tests."""

import pytest
from pytest_django.fixtures import Settings


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
