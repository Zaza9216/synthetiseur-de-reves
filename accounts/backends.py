"""Authentification par identifiant insensible à la casse."""

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.base_user import AbstractBaseUser
from django.http import HttpRequest


class CaseInsensitiveModelBackend(ModelBackend):
    """Comme ``ModelBackend``, mais « Othmane », « othmane » et « OTHMANE » sont le même compte.

    Indispensable sur iPhone : Safari met souvent une majuscule automatique à la
    première lettre des champs texte. Si d'anciens comptes ne différaient que par
    la casse, la correspondance exacte reste prioritaire.
    """

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> AbstractBaseUser | None:
        """Vérifie l'identifiant (sans tenir compte de la casse) et le mot de passe.

        Returns:
            L'utilisateur authentifié, ou ``None``.
        """
        user_model = get_user_model()
        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)
        if username is None or password is None:
            return None
        username = username.strip()
        candidates = list(user_model._default_manager.filter(username__iexact=username)[:2])
        if len(candidates) > 1:
            candidates = [c for c in candidates if c.get_username() == username]
        if not candidates:
            user_model().set_password(password)  # même durée qu'un vrai essai (pas d'indice)
            return None
        user = candidates[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
