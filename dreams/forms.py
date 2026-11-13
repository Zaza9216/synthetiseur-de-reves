"""Formulaires de l'application ``dreams``."""

from typing import Any

from django import forms
from django.conf import settings

from dreams.models import Dream, Emotion
from dreams.validators import validate_audio_file


class DreamCreateForm(forms.ModelForm):
    """Envoi d'un nouveau rêve : un fichier audio et sa durée.

    La durée est mesurée par le navigateur (enregistrement ou lecture du
    fichier). Elle sert à refuser les récits trop longs et à estimer le coût
    de la transcription ; elle est facultative pour les navigateurs sans
    JavaScript.
    """

    audio = forms.FileField(
        label="Enregistrement audio",
        validators=[validate_audio_file],
        widget=forms.ClearableFileInput(attrs={"accept": "audio/*,.webm,.m4a,.mp4"}),
    )
    audio_duration = forms.FloatField(required=False, min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = Dream
        fields = ("audio", "audio_duration")

    def clean_audio_duration(self) -> float | None:
        """Refuse les enregistrements plus longs que la durée maximale.

        Returns:
            La durée en secondes, ou ``None`` si elle est inconnue.

        Raises:
            ValidationError: Si la durée dépasse ``DREAM_AUDIO_MAX_SECONDS``.
        """
        duration = self.cleaned_data.get("audio_duration")
        max_seconds = settings.DREAM_AUDIO_MAX_SECONDS
        if duration is not None and duration > max_seconds:
            raise forms.ValidationError(
                f"L'enregistrement est trop long (maximum {max_seconds // 60} minutes)."
            )
        return duration


class DreamFilterForm(forms.Form):
    """Filtres du tableau de bord : période et émotion.

    Tous les champs sont facultatifs. Les valeurs arrivent dans l'URL
    (méthode GET) : un tableau de bord filtré peut être mis en favori.
    """

    start = forms.DateField(
        label="Du", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    end = forms.DateField(
        label="Au", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    emotion = forms.ChoiceField(
        label="Émotion",
        required=False,
        choices=[("", "Toutes les émotions"), *Emotion.choices],
    )

    def clean(self) -> dict[str, Any]:
        """Vérifie que la date de début précède la date de fin.

        Returns:
            Les données nettoyées.

        Raises:
            ValidationError: Si la période est inversée.
        """
        cleaned = super().clean()
        start, end = cleaned.get("start"), cleaned.get("end")
        if start and end and start > end:
            raise forms.ValidationError("La date de début doit précéder la date de fin.")
        return cleaned
