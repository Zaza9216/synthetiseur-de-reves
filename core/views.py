"""Vues transverses : accueil et sonde de santé."""

import logging

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from core import metrics

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
    return JsonResponse({"status": "ok", "database": "up", "version": settings.APP_VERSION})


@staff_member_required
def supervision(request: HttpRequest) -> HttpResponse:
    """Tableau de supervision réservé à l'équipe : santé, performance, coût.

    Args:
        request: Requête HTTP entrante (``?fenetre=24h|7j|30j``).

    Returns:
        La page de supervision.
    """
    window = request.GET.get("fenetre", "24h")
    if window not in metrics.WINDOWS:
        window = "24h"
    since = metrics.WINDOWS[window]
    context = {
        "window": window,
        "windows": list(metrics.WINDOWS),
        "dreams": metrics.dream_metrics(since),
        "services": metrics.service_metrics(since),
        "budget": metrics.budget_metrics(),
        "users": metrics.user_count(),
        "errors": metrics.recent_errors(),
        "version": settings.APP_VERSION,
    }
    return render(request, "core/supervision.html", context)
