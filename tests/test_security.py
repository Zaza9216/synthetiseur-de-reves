"""Tests de sécurité : protection contre la force brute et en-têtes de sécurité."""

from typing import Any

import pytest
from axes.models import AccessAttempt
from django.test import Client, RequestFactory
from django.urls import reverse

from core.security import client_ip
from tests.conftest import STRONG_PASSWORD


def attempt(client: Client, password: str, ip: str = "203.0.113.7", username: str = "bob") -> Any:
    """Tente une connexion depuis une adresse IP, telle que la transmet le proxy de Render.

    Le proxy ajoute l'adresse du visiteur à la fin de ``X-Forwarded-For``.
    """
    return client.post(
        reverse("accounts:login"),
        {"username": username, "password": password},
        HTTP_X_FORWARDED_FOR=ip,
        REMOTE_ADDR="10.0.0.1",  # adresse interne du proxy, identique pour tous
    )


# --- Force brute ----------------------------------------------------------------------


def test_login_is_blocked_after_5_failures(client: Client, user: Any) -> None:
    for _ in range(4):
        assert attempt(client, "faux").status_code == 200

    blocked = attempt(client, "faux")
    still_blocked = attempt(client, STRONG_PASSWORD)  # même le bon mot de passe

    assert blocked.status_code == 429
    assert "Trop de tentatives" in blocked.content.decode()
    assert still_blocked.status_code == 429
    assert "_auth_user_id" not in client.session


def test_lockout_is_per_ip_and_username(client: Client, user: Any) -> None:
    for _ in range(5):
        attempt(client, "faux", ip="203.0.113.7")

    other_ip = attempt(client, STRONG_PASSWORD, ip="198.51.100.20")

    assert other_ip.status_code == 302  # le vrai propriétaire, depuis chez lui, se connecte


def test_successful_login_resets_failure_counter(client: Client, user: Any) -> None:
    for _ in range(3):
        attempt(client, "faux")

    attempt(client, STRONG_PASSWORD)

    assert not AccessAttempt.objects.filter(username="bob").exists()


def test_real_ip_is_read_behind_proxy(client: Client, user: Any) -> None:
    attempt(client, "faux", ip="203.0.113.7")

    assert AccessAttempt.objects.get().ip_address == "203.0.113.7"


def test_forged_header_cannot_choose_the_ip(client: Client, user: Any) -> None:
    # L'attaquant envoie lui-même « 1.2.3.4 » ; le proxy ajoute ensuite sa vraie adresse.
    attempt(client, "faux", ip="1.2.3.4, 203.0.113.7")

    assert AccessAttempt.objects.get().ip_address == "203.0.113.7"


@pytest.mark.django_db
def test_signup_still_logs_the_user_in(client: Client) -> None:
    response = client.post(
        reverse("accounts:signup"),
        {
            "username": "alice",
            "email": "alice@example.com",
            "password1": STRONG_PASSWORD,
            "password2": STRONG_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert "_auth_user_id" in client.session


# --- En-têtes de sécurité ------------------------------------------------------------------


@pytest.mark.django_db
def test_security_headers_on_every_page(client: Client) -> None:
    response = client.get(reverse("core:home"))
    csp = response["Content-Security-Policy"]

    assert "default-src 'self'" in csp
    assert "script-src 'self' https://cdn.jsdelivr.net" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0]
    assert response["Permissions-Policy"].startswith("microphone=(self), camera=()")
    assert response["X-Frame-Options"] == "DENY"


@pytest.mark.django_db
def test_every_external_resource_is_allowed_by_csp(client: Client) -> None:
    """Chaque CDN utilisé par les gabarits doit être autorisé, sinon la page casse."""
    html = client.get(reverse("core:home")).content.decode()
    csp = client.get(reverse("core:home"))["Content-Security-Policy"]

    for host in ("https://cdn.jsdelivr.net", "https://fonts.googleapis.com"):
        assert host in html
        assert host in csp


# --- Lecture de l'adresse IP -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("forwarded", "proxies", "expected"),
    [
        ("203.0.113.7", 1, "203.0.113.7"),
        ("1.2.3.4, 203.0.113.7", 1, "203.0.113.7"),
        ("203.0.113.7, 172.16.0.5", 2, "203.0.113.7"),
        ("203.0.113.7", 2, "10.0.0.1"),  # moins d'adresses que de proxys : en-tête douteux
        ("", 1, "10.0.0.1"),
        ("203.0.113.7", 0, "10.0.0.1"),  # aucun proxy de confiance : on ignore l'en-tête
    ],
)
def test_client_ip(settings: Any, forwarded: str, proxies: int, expected: str) -> None:
    settings.TRUSTED_PROXY_COUNT = proxies
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR=forwarded, REMOTE_ADDR="10.0.0.1")

    assert client_ip(request) == expected
