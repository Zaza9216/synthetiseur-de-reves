"""Tests de l'identifiant insensible à la casse (majuscule automatique sur iPhone, #46)."""

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.urls import reverse

from accounts.backends import CaseInsensitiveModelBackend
from core.security import normalized_username
from tests.conftest import STRONG_PASSWORD

User = get_user_model()


def log_in(client: Client, username: str, password: str = STRONG_PASSWORD) -> Any:
    return client.post(
        reverse("accounts:login"),
        {"username": username, "password": password},
        HTTP_X_FORWARDED_FOR="203.0.113.7",
    )


@pytest.mark.parametrize("typed", ["bob", "Bob", "BOB", "  bob  "])
def test_login_ignores_case_and_spaces(client: Client, user: Any, typed: str) -> None:
    response = log_in(client, typed)

    assert response.status_code == 302
    assert int(client.session["_auth_user_id"]) == user.pk


def test_wrong_password_is_still_refused(client: Client, user: Any) -> None:
    assert log_in(client, "BOB", "faux").status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_signup_refuses_same_username_with_other_case(client: Client) -> None:
    User.objects.create_user("Othmane", "o@example.com", STRONG_PASSWORD)

    response = client.post(
        reverse("accounts:signup"),
        {
            "username": "othmane",
            "email": "autre@example.com",
            "password1": STRONG_PASSWORD,
            "password2": STRONG_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert User.objects.filter(username__iexact="othmane").count() == 1


def test_lockout_counts_all_casings_together(client: Client, user: Any) -> None:
    for typed in ["Bob", "bob", "BOB", "bOb"]:
        log_in(client, typed, "faux")

    assert log_in(client, "bob", "faux").status_code == 429


@pytest.mark.django_db
def test_exact_match_wins_for_legacy_duplicates() -> None:
    """Comptes créés avant le correctif et ne différant que par la casse."""
    upper = User.objects.create_user("Alex", "a1@example.com", "Mot-De-Passe-Un-2026")
    lower = User.objects.create_user("alex", "a2@example.com", "Mot-De-Passe-Deux-2026")
    backend = CaseInsensitiveModelBackend()

    assert backend.authenticate(None, username="Alex", password="Mot-De-Passe-Un-2026") == upper
    assert backend.authenticate(None, username="alex", password="Mot-De-Passe-Deux-2026") == lower
    assert backend.authenticate(None, username="ALEX", password="Mot-De-Passe-Un-2026") is None


@pytest.mark.django_db
def test_backend_rejects_missing_credentials_and_unknown_users() -> None:
    backend = CaseInsensitiveModelBackend()

    assert backend.authenticate(None, username=None, password="x") is None
    assert backend.authenticate(None, username="bob", password=None) is None
    assert backend.authenticate(None, username="inconnu", password="x") is None


def test_backend_accepts_username_as_keyword(user: Any) -> None:
    backend = CaseInsensitiveModelBackend()

    assert backend.authenticate(None, password=STRONG_PASSWORD, **{"username": "BOB"}) == user


def test_inactive_user_cannot_log_in(user: Any) -> None:
    user.is_active = False
    user.save()

    assert CaseInsensitiveModelBackend().authenticate(None, "bob", STRONG_PASSWORD) is None


def test_normalized_username_for_lockout() -> None:
    request = RequestFactory().post("/", {"username": "  Othmane "})

    assert normalized_username(request, None) == "othmane"
    assert normalized_username(request, {"username": "BOB"}) == "bob"


@pytest.mark.django_db
@pytest.mark.parametrize("url_name", ["accounts:login", "accounts:signup"])
def test_username_field_has_no_autocapitalize(client: Client, url_name: str) -> None:
    html = client.get(reverse(url_name)).content.decode()
    field = html.split('name="username"', 1)[1].split(">", 1)[0]

    assert 'autocapitalize="none"' in field
    assert 'autocorrect="off"' in field
    assert 'spellcheck="false"' in field
