"""Modèles transverses."""

from django.db import models


class StoredFile(models.Model):
    """Fichier envoyé ou généré (audio, image), stocké dans la base de données.

    Utilisé en production par ``DatabaseStorage`` : l'hébergement gratuit
    n'offre qu'un disque éphémère, effacé à chaque redémarrage. Les fichiers
    du projet sont petits (audio ≤ 10 Mo, image ≈ 55 Ko) : la base PostgreSQL
    les conserve sans service supplémentaire.
    """

    name = models.CharField("chemin", max_length=255, unique=True)
    content = models.BinaryField("contenu")
    size = models.PositiveIntegerField("taille (octets)")
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        verbose_name = "fichier stocké"
        verbose_name_plural = "fichiers stockés"

    def __str__(self) -> str:
        """Retourne le chemin du fichier."""
        return self.name
