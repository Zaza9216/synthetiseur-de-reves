"""Services d'IA simulés, pour les tests de charge.

Ils reproduisent les **durées mesurées** des vraies API (voir le journal de
bord) sans aucun appel réseau ni coût : on mesure ainsi la capacité de
l'application elle-même, pas celle d'OpenAI. Activés par ``AI_BACKEND=fake``,
ils sont interdits en production (voir ``config/settings.py``).
"""

import random
import time
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile

from dreams.ai.emotion import EmotionResult
from dreams.ai.lexicon import classify_with_lexicon
from dreams.ai.tracking import track_api_call
from dreams.models import ApiService, Dream, EmotionMethod

# Récits renvoyés par la fausse transcription.
FAKE_STORIES = (
    "Je volais au-dessus d'une ville de verre sous un ciel violet, je me sentais libre et heureux.",
    "Quelqu'un me poursuivait dans un couloir sans fin et j'avais très peur.",
    "Je revenais dans la maison de mon enfance, vide et silencieuse, j'étais triste.",
    "Mon chat parlait japonais et la cuisine se transformait en aquarium, c'était étrange.",
)
# Plus petite image WebP valide (1×1 pixel).
FAKE_WEBP = bytes.fromhex("524946461a000000574542505650384c0d0000002f00000010071011118888fe0700")


def _wait(base_seconds: float) -> None:
    """Simule la latence d'une API (±20 %), mise à l'échelle par ``AI_FAKE_LATENCY_SCALE``."""
    time.sleep(base_seconds * random.uniform(0.8, 1.2) * settings.AI_FAKE_LATENCY_SCALE)


def fake_transcribe(dream: Dream) -> str:
    """Transcription simulée (≈ 1,2 s mesurées avec gpt-4o-transcribe)."""
    with track_api_call(ApiService.TRANSCRIPTION, "fake-transcribe", dream, provider="fake"):
        _wait(1.2)
    return random.choice(FAKE_STORIES)


def fake_classify(dream: Dream) -> EmotionResult:
    """Classification simulée (≈ 0,9 s mesurées avec gpt-4o-mini), résultat du lexique."""
    with track_api_call(ApiService.EMOTION, "fake-emotion", dream, provider="fake"):
        _wait(0.9)
        emotion, score = classify_with_lexicon(dream.transcription)
    return EmotionResult(emotion, score, EmotionMethod.IA)


def fake_image(dream: Dream) -> tuple[ContentFile, str]:
    """Génération d'image simulée (≈ 10,2 s mesurées avec gpt-image-1-mini)."""
    with track_api_call(ApiService.IMAGE, "fake-image", dream, provider="fake") as call:
        _wait(10.2)
        call.cost_usd = Decimal("0")
    return ContentFile(FAKE_WEBP, name="reve.webp"), "prompt simulé"
