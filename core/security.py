"""Outils de sécurité transverses."""

from typing import Any

from django.conf import settings
from django.http import HttpRequest


def client_ip(request: HttpRequest) -> str:
    """Adresse IP réelle du visiteur, derrière le proxy de l'hébergeur.

    Chaque proxy de confiance **ajoute** l'adresse de son interlocuteur à la fin
    de l'en-tête ``X-Forwarded-For``. Avec ``TRUSTED_PROXY_COUNT`` proxys devant
    l'application, l'adresse du visiteur est donc la N-ième en partant de la fin.
    Les valeurs placées plus à gauche ont pu être écrites par le client lui-même :
    elles ne sont jamais utilisées (un attaquant ne peut pas choisir son adresse
    pour contourner le blocage des tentatives de connexion).

    Args:
        request: Requête HTTP entrante.

    Returns:
        L'adresse IP du visiteur, ou l'adresse de connexion directe à défaut.
    """
    remote_addr = request.META.get("REMOTE_ADDR", "")
    proxies = settings.TRUSTED_PROXY_COUNT
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not proxies or not forwarded:
        return remote_addr
    addresses = [address.strip() for address in forwarded.split(",") if address.strip()]
    if len(addresses) < proxies:
        return remote_addr
    return addresses[-proxies]


def normalized_username(request: HttpRequest, credentials: dict[str, Any] | None) -> str:
    """Identifiant en minuscules, pour compter les tentatives de connexion par compte.

    Sans normalisation, « Bob » et « bob » auraient chacun leur propre compteur :
    un attaquant doublerait (ou plus) son nombre d'essais.

    Args:
        request: Requête HTTP entrante.
        credentials: Identifiants transmis à l'authentification, s'il y en a.

    Returns:
        L'identifiant normalisé (chaîne vide s'il est absent).
    """
    username = (credentials or {}).get("username") or request.POST.get("username", "")
    return str(username).strip().lower()
