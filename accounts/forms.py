"""Formulaires de l'application ``accounts``."""

from typing import Any

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from accounts.models import User


class SignUpForm(UserCreationForm):
    """Formulaire d'inscription : identifiant, email et mot de passe confirmé.

    Les règles de robustesse du mot de passe (``AUTH_PASSWORD_VALIDATORS``)
    sont appliquées automatiquement par ``UserCreationForm``.
    """

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self) -> str:
        """Normalise l'email en minuscules et vérifie qu'il n'est pas déjà utilisé.

        Returns:
            L'email normalisé.

        Raises:
            ValidationError: Si un compte utilise déjà cet email.
        """
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Un compte existe déjà avec cette adresse email.")
        return email


class DeleteAccountForm(forms.Form):
    """Confirmation de la suppression du compte par le mot de passe actuel."""

    password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, user: User, *args: Any, **kwargs: Any) -> None:
        """Mémorise l'utilisateur dont on vérifie le mot de passe."""
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self) -> str:
        """Vérifie le mot de passe.

        Raises:
            ValidationError: Si le mot de passe est incorrect.
        """
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise ValidationError("Mot de passe incorrect.")
        return password
