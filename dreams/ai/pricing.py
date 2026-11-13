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
