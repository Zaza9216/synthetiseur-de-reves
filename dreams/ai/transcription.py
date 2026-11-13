"""Transcription de l'enregistrement audio d'un rêve en texte."""

from pathlib import Path

import openai
from django.conf import settings

from dreams.ai.client import get_openai_client
from dreams.ai.errors import AIServiceError, translate_openai_error
from dreams.ai.pricing import transcription_cost
from dreams.ai.tracking import track_api_call
from dreams.models import ApiService, Dream

# Contexte donné au modèle pour améliorer la ponctuation et le vocabulaire.
TRANSCRIPTION_PROMPT = "Récit d'un rêve raconté à voix haute, en français, à la première personne."


def transcribe_dream(dream: Dream) -> str:
    """Transcrit en texte l'enregistrement audio d'un rêve.

    Args:
        dream: Le rêve dont l'audio doit être transcrit.

    Returns:
        Le texte transcrit, sans espaces superflus.

    Raises:
        AIServiceError: Si l'audio est absent, si l'API échoue, ou si aucune
            parole n'a été détectée.
    """
    if not dream.audio:
        raise AIServiceError("Aucun enregistrement audio n'est associé à ce rêve.", retryable=False)

    client = get_openai_client()
    model = settings.TRANSCRIPTION_MODEL

    with dream.audio.open("rb") as audio_file:
        payload = (Path(dream.audio.name).name, audio_file.read())

    try:
        with track_api_call(ApiService.TRANSCRIPTION, model, dream) as call:
            result = client.audio.transcriptions.create(
                model=model,
                file=payload,
                language="fr",
                prompt=TRANSCRIPTION_PROMPT,
            )
            call.cost_usd = transcription_cost(model, dream.audio_duration)
    except openai.OpenAIError as error:
        raise translate_openai_error(error) from error

    text = (result.text or "").strip()
    if not text:
        raise AIServiceError(
            "Aucune parole n'a été détectée dans l'enregistrement. "
            "Vérifiez votre micro et racontez à nouveau votre rêve.",
            retryable=False,
        )
    return text
