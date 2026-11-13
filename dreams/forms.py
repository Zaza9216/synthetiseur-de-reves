"""Formulaires de l'application ``dreams``."""

from django import forms
from django.conf import settings

from dreams.models import Dream
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
