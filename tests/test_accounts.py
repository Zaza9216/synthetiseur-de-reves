"""Tests de l'inscription, de la connexion et de la déconnexion."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()
STRONG_PASSWORD = "Reve-Lucide-2026!"


def _signup_data(**overrides: str) -> dict[str, str]:
    """Construit des données d'inscription valides, surchargeables."""
    data = {
        "username": "alice",
        "email": "Alice@Example.com",
        "password1": STRONG_PASSWORD,
        "password2": STRONG_PASSWORD,
    }
    data.update(overrides)
    return data


@pytest.fixture
def user(db: None) -> User:
    """Crée un utilisateur existant."""
    return User.objects.create_user("bob", "bob@example.com", STRONG_PASSWORD)


# --- Inscription -----------------------------------------------------------------


@pytest.mark.django_db
def test_signup_page_is_reachable(client: Client) -> None:
    response = client.get(reverse("accounts:signup"))

    assert response.status_code == 200
    assert "Créer un compte" in response.content.decode()


@pytest.mark.django_db
def test_signup_creates_user_logs_in_and_normalizes_email(client: Client) -> None:
    response = client.post(reverse("accounts:signup"), _signup_data())

    assert response.status_code == 302
    created = User.objects.get(username="alice")
    assert created.email == "alice@example.com"
    assert int(client.session["_auth_user_id"]) == created.pk


@pytest.mark.django_db
def test_signup_rejects_mismatched_passwords(client: Client) -> None:
    response = client.post(reverse("accounts:signup"), _signup_data(password2="autre"))

    assert response.status_code == 200
    assert not User.objects.filter(username="alice").exists()


@pytest.mark.django_db
def test_signup_rejects_weak_password(client: Client) -> None:
    response = client.post(
        reverse("accounts:signup"), _signup_data(password1="123", password2="123")
    )

    assert response.status_code == 200
    assert not User.objects.filter(username="alice").exists()


def test_signup_rejects_duplicate_email_case_insensitive(client: Client, user: User) -> None:
    response = client.post(reverse("accounts:signup"), _signup_data(email="BOB@example.com"))

    assert response.status_code == 200
    assert "Un compte existe déjà avec cette adresse email." in response.content.decode()
    assert User.objects.count() == 1


def test_signup_redirects_already_authenticated_user(client: Client, user: User) -> None:
    client.force_login(user)

    response = client.get(reverse("accounts:signup"))

    assert response.status_code == 302


# --- Connexion / déconnexion -------------------------------------------------------


def test_login_with_valid_credentials(client: Client, user: User) -> None:
    response = client.post(
        reverse("accounts:login"), {"username": "bob", "password": STRONG_PASSWORD}
    )

    assert response.status_code == 302
    assert int(client.session["_auth_user_id"]) == user.pk


def test_login_with_wrong_password_shows_error(client: Client, user: User) -> None:
    response = client.post(reverse("accounts:login"), {"username": "bob", "password": "faux"})

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert "alert-danger" in response.content.decode()


def test_logout_ends_session(client: Client, user: User) -> None:
    client.force_login(user)

    response = client.post(reverse("accounts:logout"))

    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_navbar_shows_username_when_logged_in(client: Client, user: User) -> None:
    client.force_login(user)

    response = client.get(reverse("core:home"))

    assert "bob" in response.content.decode()
    assert "Déconnexion" in response.content.decode()
