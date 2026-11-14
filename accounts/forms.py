"""Formulaires de l'application ``accounts``."""

from typing import Any

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from accounts.models import User

# Attributs du champ identifiant : sur mobile, ni majuscule ni correction automatiques.
USERNAME_INPUT_ATTRS = {"autocapitalize": "none", "autocorrect": "off", "spellcheck": "false"}


class LoginForm(AuthenticationForm):
    """Formulaire de connexion adapté au mobile (identifiant sans majuscule automatique)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Ajoute les attributs mobiles au champ identifiant."""
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(USERNAME_INPUT_ATTRS)


class SignUpForm(UserCreationForm):
    """Formulaire d'inscription : identifiant, email et mot de passe confirmé.

    Les règles de robustesse du mot de passe (``AUTH_PASSWORD_VALIDATORS``)
    sont appliquées automatiquement par ``UserCreationForm``.
    """

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Ajoute les attributs mobiles au champ identifiant."""
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(USERNAME_INPUT_ATTRS)

    def clean_username(self) -> str:
        """Refuse un identifiant déjà pris, sans tenir compte des majuscules.

        Returns:
            L'identifiant, débarrassé des espaces superflus.

        Raises:
            ValidationError: Si « Bob » existe déjà et que l'on demande « bob ».
        """
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Cet identifiant est déjà pris.")
        return username

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
