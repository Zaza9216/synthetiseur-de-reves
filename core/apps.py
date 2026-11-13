"""Configuration de l'application ``core``."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Application transverse : page d'accueil, santé du service."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
