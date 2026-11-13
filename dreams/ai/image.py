"""Génération d'une image illustrant un rêve."""

import base64
import binascii

import openai
from django.conf import settings
from django.core.files.base import ContentFile

from dreams.ai.budget import ensure_budget_available
from dreams.ai.client import get_openai_client
from dreams.ai.errors import AIServiceError, translate_openai_error
from dreams.ai.pricing import image_cost
from dreams.ai.tracking import track_api_call
from dreams.models import ApiService, Dream, Emotion

# Le prompt n'a pas besoin du récit complet pour composer une scène.
MAX_STORY_CHARS = 1500

# Ambiance visuelle associée à chaque émotion.
EMOTION_MOODS: dict[str, str] = {
    Emotion.HEUREUX: "lumière chaude et dorée, couleurs pastel, atmosphère joyeuse et paisible",
    Emotion.STRESSANT: "contrastes marqués, ombres profondes, tons froids, tension palpable",
    Emotion.TRISTE: "brume légère, tons bleus et gris délavés, atmosphère mélancolique",
    Emotion.COLERE: "rouges et oranges intenses, ciel orageux, énergie tourmentée",
    Emotion.SURPRENANT: "couleurs vives inattendues, perspectives impossibles, touche surréaliste",
    Emotion.NEUTRE: "lumière douce et naturelle, palette équilibrée, atmosphère calme",
}

MODERATION_MESSAGE = (
    "L'image n'a pas pu être générée : le contenu du rêve a été refusé "
    "par le filtre de sécurité du service d'IA."
)


def build_image_prompt(dream: Dream) -> str:
    """Compose la description de l'image à partir du récit et de l'émotion.

    Args:
        dream: Le rêve, avec sa transcription et, si possible, son émotion.

    Returns:
        Le prompt envoyé au modèle d'image.
    """
    mood = EMOTION_MOODS.get(dream.emotion, EMOTION_MOODS[Emotion.NEUTRE])
    story = dream.transcription[:MAX_STORY_CHARS]
    return (
        "Illustration onirique d'un rêve, style peinture numérique douce et poétique. "
        f"Ambiance : {mood}. "
        "Aucun texte, aucune lettre, aucune signature dans l'image. "
        f"Scène du rêve, racontée par la personne qui l'a fait : « {story} »"
    )


def generate_dream_image(dream: Dream) -> tuple[ContentFile, str]:
    """Génère l'illustration d'un rêve.

    Args:
        dream: Le rêve à illustrer (transcription renseignée).

    Returns:
        Le fichier image (WebP) prêt à être enregistré, et le prompt utilisé.

    Raises:
        AIServiceError: Si le budget est atteint, si l'API échoue ou si le
            contenu est refusé par la modération.
    """
    ensure_budget_available()
    client = get_openai_client()
    model = settings.IMAGE_MODEL
    quality = settings.IMAGE_QUALITY
    prompt = build_image_prompt(dream)

    try:
        with track_api_call(ApiService.IMAGE, model, dream) as call:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size="1024x1024",
                quality=quality,
                output_format="webp",
                output_compression=80,
                n=1,
                timeout=settings.IMAGE_TIMEOUT,
            )
            call.cost_usd = image_cost(model, quality)
    except openai.BadRequestError as error:
        if getattr(error, "code", None) == "moderation_blocked":
            raise AIServiceError(MODERATION_MESSAGE, retryable=False) from error
        raise translate_openai_error(error) from error
    except openai.OpenAIError as error:
        raise translate_openai_error(error) from error

    try:
        image_bytes = base64.b64decode(response.data[0].b64_json, validate=True)
    except (AttributeError, IndexError, TypeError, binascii.Error) as error:
        raise AIServiceError("Le service d'image a renvoyé une réponse inattendue.") from error
    if not image_bytes:
        raise AIServiceError("Le service d'image a renvoyé une image vide.")
    return ContentFile(image_bytes, name="reve.webp"), prompt
