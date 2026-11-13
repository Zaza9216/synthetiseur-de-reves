"""Configuration de l'application ``dreams``."""

from django.apps import AppConfig


class DreamsConfig(AppConfig):
    """Rêves : enregistrement, traitement par IA, historique."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "dreams"
    verbose_name = "Rêves"

    def ready(self) -> None:
        """Enregistre les signaux de l'application au démarrage."""
        from dreams import signals  # noqa: F401
