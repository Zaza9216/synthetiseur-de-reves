"""Estimation du coût des appels aux API d'IA.

Tarifs publics OpenAI relevés en novembre 2026, en dollars US. Ce sont des
**estimations** servant au suivi du budget (≤ 20 €) : la facture réelle fait foi.
"""

from decimal import Decimal

# Transcription : prix par minute d'audio.
TRANSCRIPTION_USD_PER_MINUTE: dict[str, Decimal] = {
    "gpt-4o-mini-transcribe": Decimal("0.003"),
    "gpt-4o-transcribe": Decimal("0.006"),
    "whisper-1": Decimal("0.006"),
}

# Durée supposée quand le navigateur n'a pas pu mesurer l'audio.
DEFAULT_AUDIO_MINUTES = Decimal("1")


def transcription_cost(model: str, duration_seconds: float | None) -> Decimal:
    """Estime le coût d'une transcription.

    Args:
        model: Nom du modèle de transcription.
        duration_seconds: Durée de l'audio en secondes, ou ``None`` si inconnue.

    Returns:
        Le coût estimé en dollars US.
    """
    minutes = (
        Decimal(str(duration_seconds)) / 60
        if duration_seconds is not None
        else DEFAULT_AUDIO_MINUTES
    )
    rate = TRANSCRIPTION_USD_PER_MINUTE.get(model, Decimal("0.006"))
    return (minutes * rate).quantize(Decimal("0.000001"))


# Modèles de langage : prix par million de jetons (entrée, sortie).
CHAT_USD_PER_MILLION_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
}


def chat_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Estime le coût d'un appel à un modèle de langage.

    Args:
        model: Nom du modèle.
        input_tokens: Nombre de jetons envoyés.
        output_tokens: Nombre de jetons générés.

    Returns:
        Le coût estimé en dollars US.
    """
    input_rate, output_rate = CHAT_USD_PER_MILLION_TOKENS.get(
        model, (Decimal("2.50"), Decimal("10.00"))
    )
    cost = (input_tokens * input_rate + output_tokens * output_rate) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


# Génération d'images 1024×1024 : prix par image selon la qualité.
IMAGE_USD_PER_IMAGE: dict[str, dict[str, Decimal]] = {
    "gpt-image-1-mini": {
        "low": Decimal("0.005"),
        "medium": Decimal("0.011"),
        "high": Decimal("0.036"),
    },
    "gpt-image-1": {"low": Decimal("0.011"), "medium": Decimal("0.042"), "high": Decimal("0.167")},
}


def image_cost(model: str, quality: str) -> Decimal:
    """Estime le coût de génération d'une image 1024×1024.

    Args:
        model: Nom du modèle d'image.
        quality: Qualité demandée (``low``, ``medium`` ou ``high``).

    Returns:
        Le coût estimé en dollars US (tarif le plus élevé connu si le
        modèle ou la qualité sont inconnus, par prudence).
    """
    return IMAGE_USD_PER_IMAGE.get(model, {}).get(quality, Decimal("0.167"))
