"""Modèle utilisateur du projet."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Utilisateur de l'application.

    Modèle personnalisé dès le départ (recommandation officielle de Django) :
    il permet de faire évoluer le profil plus tard sans migration complexe.
    L'email est obligatoire et unique.
    """

    email = models.EmailField("adresse email", unique=True)

    def __str__(self) -> str:
        """Retourne l'identifiant de l'utilisateur."""
        return self.username
