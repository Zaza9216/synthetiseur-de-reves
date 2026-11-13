"""Vues transverses : accueil et sonde de santé."""

import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def home(request: HttpRequest) -> HttpResponse:
    """Affiche la page d'accueil.

    Args:
        request: Requête HTTP entrante.

    Returns:
        La page d'accueil rendue.
    """
    return render(request, "core/home.html")


def health(request: HttpRequest) -> JsonResponse:
    """Indique si le service et sa base de données répondent.

    Utilisée par la plateforme d'hébergement et le monitoring pour savoir
    si l'application est en vie.

    Args:
        request: Requête HTTP entrante.

    Returns:
        ``{"status": "ok"}`` avec un code 200 si la base répond,
        ``{"status": "error"}`` avec un code 503 sinon.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        logger.exception("Health check : base de données injoignable")
        return JsonResponse({"status": "error", "database": "down"}, status=503)
    return JsonResponse({"status": "ok", "database": "up"})
