"""Configuration de l'application ``accounts``."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Gestion des comptes : inscription, connexion, déconnexion."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Comptes"
