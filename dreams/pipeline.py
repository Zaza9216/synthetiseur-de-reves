"""Pipeline de traitement d'un rêve : transcription → émotion → image.

Le traitement est **reprenable** : chaque étape déjà réussie (son résultat est
enregistré sur le rêve) est sautée. Relancer un rêve en échec reprend donc à
l'étape qui a échoué, sans refacturer les appels déjà payés.

Le traitement s'exécute en arrière-plan, dans un fil d'exécution du serveur,
pour que l'utilisateur ne reste pas bloqué devant une page qui charge. La
fonction ``enqueue_dream`` isole ce choix : passer plus tard à une vraie file
de tâches (Celery, RQ…) ne demandera de modifier qu'elle.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from dreams.ai.emotion import classify_dream_emotion
from dreams.ai.errors import AIServiceError
from dreams.ai.image import generate_dream_image
from dreams.ai.transcription import transcribe_dream
from dreams.models import Dream, Status

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "Une erreur inattendue est survenue pendant le traitement. Réessayez."


@dataclass(frozen=True)
class Step:
    """Une étape du pipeline.

    Attributes:
        status: Statut affiché pendant l'étape.
        is_done: Indique si le résultat de l'étape est déjà présent sur le rêve.
        run: Exécute l'étape et enregistre son résultat sur le rêve (sans sauvegarder).
        fields: Champs du rêve modifiés par l'étape, sauvegardés à la fin de l'étape.
        optional: Si ``True``, un échec de l'étape n'empêche pas de terminer le
            rêve : il est signalé à l'utilisateur, qui peut relancer l'étape.
    """

    status: Status
    is_done: Callable[[Dream], bool]
    run: Callable[[Dream], None]
    fields: tuple[str, ...]
    optional: bool = False


def _run_transcription(dream: Dream) -> None:
    dream.transcription = transcribe_dream(dream)


def _run_emotion(dream: Dream) -> None:
    result = classify_dream_emotion(dream)
    dream.emotion = result.emotion
    dream.emotion_score = result.score
    dream.emotion_method = result.method


def _run_image(dream: Dream) -> None:
    image, prompt = generate_dream_image(dream)
    dream.image.save(image.name, image, save=False)
    dream.image_prompt = prompt


STEPS: tuple[Step, ...] = (
    Step(
        Status.TRANSCRIPTION,
        lambda d: bool(d.transcription),
        _run_transcription,
        ("transcription",),
    ),
    Step(
        Status.ANALYSE,
        lambda d: bool(d.emotion),
        _run_emotion,
        ("emotion", "emotion_score", "emotion_method"),
    ),
    Step(
        Status.GENERATION,
        lambda d: bool(d.image),
        _run_image,
        ("image", "image_prompt"),
        optional=True,
    ),
)


class DreamDeletedError(Exception):
    """Le rêve a été supprimé par l'utilisateur pendant son traitement."""


def _save(dream: Dream, *fields: str) -> None:
    """Enregistre uniquement les champs indiqués, si le rêve existe toujours.

    Une mise à jour ciblée (``UPDATE … WHERE id = …``) ne recrée jamais une
    ligne supprimée, contrairement à ``save()`` qui ferait un ``INSERT``.

    Raises:
        DreamDeletedError: Si le rêve n'existe plus en base.
    """
    values = {field: getattr(dream, field) for field in fields}
    if not Dream.objects.filter(pk=dream.pk).update(**values, updated_at=timezone.now()):
        raise DreamDeletedError


def process_dream(dream_id: int) -> None:
    """Exécute toutes les étapes manquantes du traitement d'un rêve.

    Le rêve doit être au statut « en attente » : il est d'abord « réservé »
    par une mise à jour conditionnelle, ce qui empêche deux traitements
    simultanés du même rêve (double clic sur « Relancer », par exemple).

    N'importe quelle erreur fait passer le rêve au statut « échec » avec un
    message clair : la fonction ne lève jamais d'exception.

    Args:
        dream_id: Identifiant du rêve à traiter.
    """
    first_status = next((step.status for step in STEPS), Status.TERMINE)
    claimed = Dream.objects.filter(pk=dream_id, status=Status.EN_ATTENTE).update(
        status=first_status, error_message="", updated_at=timezone.now()
    )
    if not claimed:
        logger.info("Rêve %s déjà en cours de traitement ou introuvable : ignoré", dream_id)
        return

    dream = Dream.objects.filter(pk=dream_id).first()
    if dream is None:
        return
    logger.info("Début du traitement du rêve %s", dream_id)
    warnings: list[str] = []
    try:
        for step in STEPS:
            if step.is_done(dream):
                continue
            dream.status = step.status
            _save(dream, "status")
            try:
                step.run(dream)
            except AIServiceError as error:
                if not step.optional:
                    raise
                logger.warning(
                    "Rêve %s : étape facultative %s échouée : %s", dream_id, step.status, error
                )
                warnings.append(error.user_message)
                continue
            _save(dream, *step.fields)
        dream.status = Status.TERMINE
        dream.processed_at = timezone.now()
        dream.error_message = " ".join(warnings)
        _save(dream, "status", "processed_at", "error_message")
    except DreamDeletedError:
        logger.info("Rêve %s supprimé pendant son traitement : arrêt", dream_id)
        if dream.image:  # fichier créé pendant ce traitement, désormais orphelin
            dream.image.storage.delete(dream.image.name)
        return
    except AIServiceError as error:
        logger.warning("Rêve %s en échec à l'étape %s : %s", dream_id, dream.status, error)
        _mark_failed(dream, error.user_message)
        return
    except Exception:
        logger.exception("Erreur inattendue pendant le traitement du rêve %s", dream_id)
        _mark_failed(dream, GENERIC_ERROR_MESSAGE)
        return

    duration = (dream.processed_at - dream.created_at).total_seconds()
    logger.info("Rêve %s traité en %.1f s depuis sa création", dream_id, duration)


def _mark_failed(dream: Dream, message: str) -> None:
    Dream.objects.filter(pk=dream.pk).update(
        status=Status.ECHEC, error_message=message, updated_at=timezone.now()
    )


@cache
def _executor() -> ThreadPoolExecutor:
    """Pool de fils d'exécution partagé, créé au premier usage."""
    return ThreadPoolExecutor(
        max_workers=settings.DREAM_PROCESSING_WORKERS, thread_name_prefix="dream"
    )


def _process_in_thread(dream_id: int) -> None:
    """Traite un rêve dans un fil dédié, puis libère sa connexion à la base."""
    try:
        process_dream(dream_id)
    finally:
        close_old_connections()


def enqueue_dream(dream_id: int) -> None:
    """Planifie le traitement d'un rêve selon ``DREAM_PROCESSING_MODE``.

    - ``"thread"`` : en arrière-plan, une fois la transaction en cours validée
      (le fil voit ainsi le rêve en base) ;
    - ``"sync"`` : immédiatement, dans la requête (débogage) ;
    - ``"off"`` : aucun traitement automatique (tests).

    Args:
        dream_id: Identifiant du rêve à traiter.
    """
    mode = settings.DREAM_PROCESSING_MODE
    if mode == "off":
        return
    if mode == "sync":
        process_dream(dream_id)
        return
    transaction.on_commit(lambda: _executor().submit(_process_in_thread, dream_id))


def retry_dream(dream: Dream) -> bool:
    """Remet un rêve en échec (ou bloqué) dans la file de traitement.

    Args:
        dream: Le rêve à relancer.

    Returns:
        ``True`` si le rêve a été relancé, ``False`` s'il n'était pas relançable.
    """
    if not dream.can_retry:
        return False
    updated = Dream.objects.filter(pk=dream.pk, status=dream.status).update(
        status=Status.EN_ATTENTE, error_message="", updated_at=timezone.now()
    )
    if updated:
        logger.info("Rêve %s relancé par l'utilisateur", dream.pk)
        enqueue_dream(dream.pk)
    return bool(updated)
