"""Tests de la classification émotionnelle : IA, lexique de secours, pipeline."""

import json
from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx2
import openai
import pytest
from django.test import Client
from django.urls import reverse

from dreams.ai.emotion import (
    MAX_INPUT_CHARS,
    RESPONSE_SCHEMA,
    classify_dream_emotion,
)
from dreams.ai.lexicon import MAX_LEXICON_SCORE, NEUTRAL_SCORE, classify_with_lexicon
from dreams.ai.pricing import chat_cost
from dreams.models import ApiCall, Dream, Emotion, EmotionMethod, Status
from dreams.pipeline import process_dream
from tests.conftest import fake_audio

MakeDream = Callable[..., Dream]
REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")


def chat_response(content: str, prompt_tokens: int = 300, completion_tokens: int = 12) -> Any:
    """Construit une réponse simulée de l'API de chat."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


@pytest.fixture
def fake_client() -> Any:
    """Remplace le client OpenAI du module d'émotion."""
    client = MagicMock()
    with patch("dreams.ai.emotion.get_openai_client", return_value=client):
        yield client


@pytest.fixture
def dream(user: Any, make_dream: MakeDream) -> Dream:
    """Rêve transcrit, pas encore analysé."""
    return make_dream(
        user,
        transcription="Je courais dans un couloir sans fin, j'avais très peur.",
        emotion="",
        emotion_score=None,
    )


# --- Lexique de secours ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("On riait au soleil, tout était doux et lumineux.", Emotion.HEUREUX),
        ("Un monstre me poursuivait, j'étais terrifié.", Emotion.STRESSANT),
        ("Je pleurais, seul dans une maison vide.", Emotion.TRISTE),
        ("J'étais furieux, c'était tellement injuste, on s'est disputés.", Emotion.COLERE),
        ("Tout était étrange : la cuisine se transformait, c'était absurde.", Emotion.SURPRENANT),
        ("J'ai acheté du pain et du lait.", Emotion.NEUTRE),
    ],
)
def test_lexicon_detects_each_emotion(text: str, expected: str) -> None:
    emotion, _ = classify_with_lexicon(text)

    assert emotion == expected


def test_lexicon_ignores_accents_and_case() -> None:
    assert classify_with_lexicon("TERRIFIÉ, ANGOISSÉ")[0] == Emotion.STRESSANT


def test_lexicon_avoids_false_positives_on_short_stems() -> None:
    # « cristal » ne doit pas compter comme « crier », ni « voleur » comme « voler ».
    assert classify_with_lexicon("Un voleur regardait un vase de cristal.") == (
        Emotion.NEUTRE,
        NEUTRAL_SCORE,
    )


def test_lexicon_score_is_capped_and_proportional() -> None:
    _, single = classify_with_lexicon("J'avais peur, très peur, une peur immense.")
    _, mixed = classify_with_lexicon("J'avais peur mais j'étais heureux.")

    assert single == MAX_LEXICON_SCORE
    assert mixed == 0.5


# --- Coût ----------------------------------------------------------------------------------


def test_chat_cost() -> None:
    assert chat_cost("gpt-4o-mini", 1_000_000, 0) == Decimal("0.150000")
    assert chat_cost("gpt-4o-mini", 300, 12) == Decimal("0.000052")
    assert chat_cost("modele-inconnu", 1_000_000, 0) == Decimal("2.500000")


# --- Classification par l'IA ------------------------------------------------------------------


def test_ai_classification_uses_strict_schema_and_records_cost(
    fake_client: Any, dream: Dream
) -> None:
    fake_client.chat.completions.create.return_value = chat_response(
        json.dumps({"emotion": "stressant", "confidence": 0.93})
    )

    result = classify_dream_emotion(dream)

    assert (result.emotion, result.score, result.method) == ("stressant", 0.93, EmotionMethod.IA)
    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == RESPONSE_SCHEMA
    assert kwargs["temperature"] == 0
    assert dream.transcription in kwargs["messages"][1]["content"]
    call = ApiCall.objects.get()
    assert call.success and call.provider == "openai"
    assert call.cost_usd == Decimal("0.000052")


def test_schema_only_allows_known_emotions() -> None:
    schema = RESPONSE_SCHEMA["json_schema"]["schema"]

    assert RESPONSE_SCHEMA["json_schema"]["strict"] is True
    assert schema["properties"]["emotion"]["enum"] == list(Emotion.values)


def test_long_transcription_is_truncated(fake_client: Any, dream: Dream) -> None:
    dream.transcription = "a" * (MAX_INPUT_CHARS + 500)
    fake_client.chat.completions.create.return_value = chat_response(
        json.dumps({"emotion": "neutre", "confidence": 0.6})
    )

    classify_dream_emotion(dream)

    sent = fake_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert sent.count("a") <= MAX_INPUT_CHARS + 5


def test_confidence_is_clamped_between_0_and_1(fake_client: Any, dream: Dream) -> None:
    fake_client.chat.completions.create.return_value = chat_response(
        json.dumps({"emotion": "heureux", "confidence": 1.7})
    )

    assert classify_dream_emotion(dream).score == 1.0


@pytest.mark.parametrize(
    "failure",
    [
        openai.APITimeoutError(request=REQUEST),
        openai.RateLimitError(
            "quota",
            response=httpx2.Response(429, request=REQUEST),
            body={"code": "insufficient_quota"},
        ),
    ],
)
def test_api_failure_falls_back_to_lexicon(
    fake_client: Any, dream: Dream, failure: Exception
) -> None:
    fake_client.chat.completions.create.side_effect = failure

    result = classify_dream_emotion(dream)

    assert result.method == EmotionMethod.LEXIQUE
    assert result.emotion == Emotion.STRESSANT
    calls = {(c.provider, c.success) for c in ApiCall.objects.all()}
    assert calls == {("openai", False), ("local", True)}


@pytest.mark.parametrize(
    "content",
    ["pas du json", json.dumps({"emotion": "euphorique", "confidence": 0.9}), json.dumps({})],
)
def test_unusable_ai_answer_falls_back_to_lexicon(
    fake_client: Any, dream: Dream, content: str
) -> None:
    fake_client.chat.completions.create.return_value = chat_response(content)

    assert classify_dream_emotion(dream).method == EmotionMethod.LEXIQUE


def test_missing_api_key_falls_back_to_lexicon(dream: Dream, settings: Any) -> None:
    settings.OPENAI_API_KEY = ""

    assert classify_dream_emotion(dream).method == EmotionMethod.LEXIQUE


# --- Intégration au pipeline -----------------------------------------------------------------


def test_pipeline_transcribes_then_classifies(
    fake_client: Any, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(
        user,
        audio=fake_audio(),
        transcription="",
        emotion="",
        emotion_score=None,
        status=Status.EN_ATTENTE,
    )
    fake_client.chat.completions.create.return_value = chat_response(
        json.dumps({"emotion": "triste", "confidence": 0.81})
    )

    with patch("dreams.pipeline.transcribe_dream", return_value="Je pleurais sous la pluie."):
        process_dream(dream.pk)

    dream.refresh_from_db()
    assert dream.status == Status.TERMINE
    assert (dream.emotion, dream.emotion_score, dream.emotion_method) == ("triste", 0.81, "ia")


def test_pipeline_does_not_reclassify_known_emotion(
    fake_client: Any, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(user, emotion="heureux", status=Status.EN_ATTENTE)

    process_dream(dream.pk)

    fake_client.chat.completions.create.assert_not_called()


def test_detail_mentions_fallback_method(client: Client, user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, emotion_method=EmotionMethod.LEXIQUE)
    client.force_login(user)

    html = client.get(reverse("dreams:detail", args=[dream.pk])).content.decode()

    assert "analyse de secours" in html
