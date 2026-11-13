"""Journalisation des appels aux API d'IA (durée, résultat, coût)."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter

from dreams.models import ApiCall, Dream

logger = logging.getLogger(__name__)


@dataclass
class CallTracker:
    """Informations complétées par l'appelant pendant l'appel.

    Attributes:
        cost_usd: Coût estimé de l'appel, à renseigner en cas de succès.
    """

    cost_usd: Decimal = Decimal("0")


@contextmanager
def track_api_call(
    service: str, model_name: str, dream: Dream | None = None, provider: str = "openai"
) -> Iterator[CallTracker]:
    """Mesure et enregistre un appel à une API d'IA.

    Exemple :

        with track_api_call(ApiService.TRANSCRIPTION, "gpt-4o-mini-transcribe", dream) as call:
            result = client.audio.transcriptions.create(...)
            call.cost_usd = transcription_cost(...)

    En cas d'exception, l'appel est enregistré comme un échec (coût nul,
    type d'erreur conservé) puis l'exception est relancée.

    Args:
        service: Service appelé (voir ``ApiService``).
        model_name: Nom du modèle utilisé.
        dream: Rêve concerné, s'il y en a un.
        provider: Fournisseur de l'API.

    Yields:
        Un ``CallTracker`` dont l'appelant renseigne le coût.
    """
    tracker = CallTracker()
    start = perf_counter()
    try:
        yield tracker
    except Exception as error:
        duration_ms = int((perf_counter() - start) * 1000)
        ApiCall.objects.create(
            dream=dream,
            service=service,
            provider=provider,
            model_name=model_name,
            success=False,
            duration_ms=duration_ms,
            error_type=type(error).__name__,
        )
        logger.warning(
            "Appel %s/%s échoué en %d ms : %s",
            service,
            model_name,
            duration_ms,
            type(error).__name__,
        )
        raise
    duration_ms = int((perf_counter() - start) * 1000)
    ApiCall.objects.create(
        dream=dream,
        service=service,
        provider=provider,
        model_name=model_name,
        success=True,
        duration_ms=duration_ms,
        cost_usd=tracker.cost_usd,
    )
    logger.info(
        "Appel %s/%s réussi en %d ms (≈ %s $)", service, model_name, duration_ms, tracker.cost_usd
    )
