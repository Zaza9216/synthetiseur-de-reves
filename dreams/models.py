"""Modèle de données des rêves."""

import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import Truncator


class Emotion(models.TextChoices):
    """Émotions reconnues dans un rêve.

    Ces six catégories correspondent aux sorties des modèles de classification
    d'émotions courants (joie, peur, tristesse, colère, surprise, neutre).
    """

    HEUREUX = "heureux", "Heureux"
    STRESSANT = "stressant", "Stressant"
    TRISTE = "triste", "Triste"
    COLERE = "colere", "En colère"
    SURPRENANT = "surprenant", "Surprenant"
    NEUTRE = "neutre", "Neutre"


class EmotionStyle(NamedTuple):
    """Apparence d'une émotion dans l'interface."""

    icon: str
    color: str


EMOTION_STYLES: dict[str, EmotionStyle] = {
    Emotion.HEUREUX: EmotionStyle("bi-emoji-laughing", "success"),
    Emotion.STRESSANT: EmotionStyle("bi-lightning-charge", "danger"),
    Emotion.TRISTE: EmotionStyle("bi-cloud-drizzle", "primary"),
    Emotion.COLERE: EmotionStyle("bi-fire", "warning"),
    Emotion.SURPRENANT: EmotionStyle("bi-stars", "info"),
    Emotion.NEUTRE: EmotionStyle("bi-emoji-neutral", "secondary"),
}
UNKNOWN_EMOTION_STYLE = EmotionStyle("bi-question-circle", "light")


class Status(models.TextChoices):
    """Étapes du traitement d'un rêve, de l'envoi de l'audio au résultat final."""

    EN_ATTENTE = "en_attente", "En attente"
    TRANSCRIPTION = "transcription", "Transcription en cours"
    ANALYSE = "analyse", "Analyse de l'émotion"
    GENERATION = "generation", "Génération de l'image"
    TERMINE = "termine", "Terminé"
    ECHEC = "echec", "Échec"


def _random_filename(folder: str, filename: str) -> str:
    """Construit un chemin de stockage anonyme pour un fichier envoyé.

    Le nom d'origine est remplacé par un identifiant aléatoire : il ne doit
    révéler ni l'utilisateur ni le contenu du rêve (RGPD).

    Args:
        folder: Dossier de destination dans le stockage des médias.
        filename: Nom du fichier d'origine (seule son extension est gardée).

    Returns:
        Le chemin relatif du fichier, par exemple ``dreams/audio/2026/11/<uuid>.webm``.
    """
    extension = Path(filename).suffix.lower()
    return f"dreams/{folder}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}"


def audio_upload_path(instance: "Dream", filename: str) -> str:
    """Chemin de stockage de l'enregistrement audio d'un rêve."""
    return _random_filename("audio", filename)


def image_upload_path(instance: "Dream", filename: str) -> str:
    """Chemin de stockage de l'image générée d'un rêve."""
    return _random_filename("images", filename)


class Dream(models.Model):
    """Un rêve raconté par un utilisateur et les résultats de son traitement."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dreams",
        verbose_name="utilisateur",
    )
    audio = models.FileField("enregistrement audio", upload_to=audio_upload_path, blank=True)
    audio_duration = models.FloatField(
        "durée de l'audio (s)",
        null=True,
        blank=True,
        help_text="Durée mesurée par le navigateur ; sert à estimer le coût de transcription.",
    )
    transcription = models.TextField("transcription", blank=True)
    emotion = models.CharField("émotion", max_length=20, choices=Emotion.choices, blank=True)
    emotion_score = models.FloatField(
        "confiance de l'émotion",
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Score de confiance du classifieur, entre 0 et 1.",
    )
    image = models.FileField("image générée", upload_to=image_upload_path, blank=True)
    image_prompt = models.TextField("prompt de l'image", blank=True)
    status = models.CharField(
        "statut", max_length=20, choices=Status.choices, default=Status.EN_ATTENTE
    )
    error_message = models.TextField("message d'erreur", blank=True)
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)
    processed_at = models.DateTimeField("traité le", null=True, blank=True)

    class Meta:
        verbose_name = "rêve"
        verbose_name_plural = "rêves"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="dream_user_date_idx"),
            models.Index(fields=["user", "emotion"], name="dream_user_emotion_idx"),
        ]

    def __str__(self) -> str:
        """Retourne le titre du rêve."""
        return self.title

    @property
    def title(self) -> str:
        """Titre court du rêve : début de la transcription, ou sa date à défaut."""
        if self.transcription:
            return Truncator(self.transcription).words(8)
        if self.created_at:
            return f"Rêve du {date_format(self.created_at, 'j F Y')}"
        return "Nouveau rêve"

    @property
    def emotion_style(self) -> EmotionStyle:
        """Icône et couleur Bootstrap associées à l'émotion du rêve."""
        return EMOTION_STYLES.get(self.emotion, UNKNOWN_EMOTION_STYLE)

    @property
    def is_processing(self) -> bool:
        """Indique si le traitement du rêve est encore en cours."""
        return self.status not in (Status.TERMINE, Status.ECHEC)

    @property
    def is_stalled(self) -> bool:
        """Indique si un traitement en cours semble bloqué.

        Le traitement tourne dans un fil d'exécution du serveur : il peut être
        interrompu par un redémarrage. Au-delà de ``DREAM_STALLED_MINUTES``
        sans progression, l'utilisateur peut le relancer.
        """
        if not self.is_processing or self.updated_at is None:
            return False
        limit = timedelta(minutes=settings.DREAM_STALLED_MINUTES)
        return timezone.now() - self.updated_at > limit

    @property
    def can_retry(self) -> bool:
        """Indique si l'utilisateur peut relancer le traitement du rêve."""
        return self.status == Status.ECHEC or self.is_stalled

    @property
    def emotion_percent(self) -> int | None:
        """Score de confiance exprimé en pourcentage entier, ou ``None``."""
        if self.emotion_score is None:
            return None
        return round(self.emotion_score * 100)


class ApiService(models.TextChoices):
    """Services d'IA appelés pendant le traitement d'un rêve."""

    TRANSCRIPTION = "transcription", "Transcription"
    EMOTION = "emotion", "Émotion"
    IMAGE = "image", "Image"


class ApiCall(models.Model):
    """Journal d'un appel à une API d'IA : durée, résultat, coût estimé.

    Sert au monitoring (latence, taux d'échec) et au suivi du budget. Les
    appels sont conservés si le rêve est supprimé (``SET_NULL``) : la dépense
    a bien eu lieu et doit rester comptabilisée.
    """

    dream = models.ForeignKey(
        Dream,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_calls",
        verbose_name="rêve",
    )
    service = models.CharField("service", max_length=20, choices=ApiService.choices)
    provider = models.CharField("fournisseur", max_length=30, default="openai")
    model_name = models.CharField("modèle", max_length=60)
    success = models.BooleanField("succès")
    duration_ms = models.PositiveIntegerField("durée (ms)")
    cost_usd = models.DecimalField(
        "coût estimé ($)", max_digits=10, decimal_places=6, default=Decimal("0")
    )
    error_type = models.CharField("type d'erreur", max_length=80, blank=True)
    created_at = models.DateTimeField("appelé le", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "appel API"
        verbose_name_plural = "appels API"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Résumé lisible de l'appel."""
        result = "OK" if self.success else f"échec ({self.error_type})"
        return f"{self.get_service_display()} · {self.model_name} · {result}"
