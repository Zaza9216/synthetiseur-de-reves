"""Stockage des fichiers dans la base de données (production)."""

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from core.models import StoredFile


@deconstructible
class DatabaseStorage(Storage):
    """Stockage Django qui enregistre le contenu des fichiers en base.

    Les URL pointent vers ``MEDIA_URL`` : elles sont servies par une vue
    protégée qui vérifie que l'utilisateur a le droit d'accéder au fichier.
    """

    def _open(self, name: str, mode: str = "rb") -> File:
        """Ouvre un fichier en lecture.

        Raises:
            FileNotFoundError: Si aucun fichier ne porte ce nom.
        """
        try:
            stored = StoredFile.objects.get(name=name)
        except StoredFile.DoesNotExist as error:
            raise FileNotFoundError(name) from error
        return ContentFile(bytes(stored.content), name=name)

    def _save(self, name: str, content: File) -> str:
        """Enregistre le contenu sous le nom donné (rendu unique par ``save``)."""
        content.seek(0)
        data = content.read()
        StoredFile.objects.create(name=name, content=data, size=len(data))
        return name

    def exists(self, name: str) -> bool:
        """Indique si un fichier porte déjà ce nom."""
        return StoredFile.objects.filter(name=name).exists()

    def delete(self, name: str) -> None:
        """Supprime le fichier s'il existe."""
        StoredFile.objects.filter(name=name).delete()

    def size(self, name: str) -> int:
        """Taille du fichier en octets.

        Raises:
            FileNotFoundError: Si aucun fichier ne porte ce nom.
        """
        size = StoredFile.objects.filter(name=name).values_list("size", flat=True).first()
        if size is None:
            raise FileNotFoundError(name)
        return size

    def url(self, name: str | None) -> str:
        """Adresse du fichier, servie par la vue protégée."""
        return f"{settings.MEDIA_URL}{name}"
