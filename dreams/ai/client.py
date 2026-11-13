"""Client OpenAI partagé, configuré avec timeout et nouvelles tentatives."""

from functools import cache

import openai
from django.conf import settings

from dreams.ai.errors import AIServiceError


@cache
def _build_client(api_key: str, timeout: float, max_retries: int) -> openai.OpenAI:
    """Crée (une seule fois par configuration) le client OpenAI.

    Le client réutilise ses connexions HTTP entre les appels.
    """
    return openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)


def get_openai_client() -> openai.OpenAI:
    """Retourne le client OpenAI configuré depuis les réglages Django.

    Le SDK refait automatiquement jusqu'à ``OPENAI_MAX_RETRIES`` tentatives,
    avec un délai croissant, sur les erreurs temporaires (timeout, coupure
    réseau, HTTP 429 et 5xx).

    Returns:
        Le client OpenAI.

    Raises:
        AIServiceError: Si aucune clé API n'est configurée.
    """
    if not settings.OPENAI_API_KEY:
        raise AIServiceError("Le service d'IA n'est pas configuré.", retryable=False)
    return _build_client(
        settings.OPENAI_API_KEY, settings.OPENAI_TIMEOUT, settings.OPENAI_MAX_RETRIES
    )
