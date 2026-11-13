"""Commande ``ensure_admin`` : crée le compte administrateur s'il n'existe pas.

L'hébergement gratuit ne donne pas accès à un terminal sur le serveur. Le
compte est donc créé au démarrage à partir de variables d'environnement :
``ADMIN_USERNAME``, ``ADMIN_EMAIL`` et ``ADMIN_PASSWORD``. Sans elles, la
commande ne fait rien. Un compte existant n'est jamais modifié.
"""

from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Crée le super-utilisateur défini par les variables d'environnement."""

    help = "Crée le compte administrateur défini par ADMIN_USERNAME / ADMIN_PASSWORD."

    def handle(self, *args: Any, **options: Any) -> None:
        """Crée le compte si les variables sont définies et qu'il n'existe pas."""
        username = settings.ADMIN_USERNAME
        password = settings.ADMIN_PASSWORD
        if not username or not password:
            self.stdout.write("ADMIN_USERNAME / ADMIN_PASSWORD non définis : rien à faire.")
            return

        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            self.stdout.write(f"Le compte administrateur « {username} » existe déjà.")
            return

        try:
            validate_password(password)
        except Exception as error:
            raise CommandError(f"Mot de passe administrateur trop faible : {error}") from error
        user_model.objects.create_superuser(
            username=username,
            email=settings.ADMIN_EMAIL or f"{username}@localhost",
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f"Compte administrateur « {username} » créé."))
