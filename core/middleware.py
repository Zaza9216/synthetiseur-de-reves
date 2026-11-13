"""Middlewares transverses : sonde de santé et mesure des requêtes lentes."""

import logging
from collections.abc import Callable
from time import perf_counter

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from core.views import health

logger = logging.getLogger("core.requests")


class HealthCheckMiddleware:
    """Répond à ``/health/`` avant toute autre vérification.

    La sonde de l'hébergeur appelle le service par son adresse interne :
    l'en-tête ``Host`` ne figure pas dans ``ALLOWED_HOSTS`` et Django
    répondrait 400. Ce middleware, placé en premier, court-circuite ce
    contrôle pour cette seule URL, qui ne renvoie aucune donnée sensible.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Mémorise le maillon suivant de la chaîne de middlewares."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Traite la sonde de santé, ou passe la main au reste de l'application."""
        if request.path == "/health/":
            return health(request)
        return self.get_response(request)


class RequestTimingMiddleware:
    """Mesure la durée de chaque requête et journalise les requêtes lentes.

    Ajoute aussi l'en-tête standard ``Server-Timing``, visible dans les outils
    de développement du navigateur.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Mémorise le maillon suivant de la chaîne de middlewares."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Chronomètre la requête et journalise si elle dépasse le seuil."""
        start = perf_counter()
        response = self.get_response(request)
        duration_ms = (perf_counter() - start) * 1000
        response["Server-Timing"] = f"app;dur={duration_ms:.1f}"
        if duration_ms >= settings.SLOW_REQUEST_MS:
            logger.warning(
                "Requête lente : %s %s → %s en %.0f ms",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                extra={"duration_ms": round(duration_ms), "status": response.status_code},
            )
        return response
