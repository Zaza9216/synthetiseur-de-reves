"""Formulaires de l'application ``accounts``."""

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
