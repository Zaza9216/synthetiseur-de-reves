"""Tests de l'application ``core`` : accueil et sonde de santé."""

from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_home_page_is_reachable(client: Client) -> None:
    """La page d'accueil répond 200 et affiche le nom de l'application."""
    response = client.get(reverse("core:home"))

    assert response.status_code == 200
    assert "Synthétiseur de rêves" in response.content.decode()


@pytest.mark.django_db
def test_health_returns_ok_when_database_is_up(client: Client) -> None:
    """La sonde de santé répond 200 quand la base est joignable."""
    response = client.get(reverse("core:health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "up"}


@pytest.mark.django_db
def test_health_returns_503_when_database_is_down(client: Client) -> None:
    """La sonde de santé répond 503 quand la base est injoignable."""
    with patch("core.views.connection.cursor", side_effect=DatabaseError("down")):
        response = client.get(reverse("core:health"))

    assert response.status_code == 503
    assert response.json()["status"] == "error"
