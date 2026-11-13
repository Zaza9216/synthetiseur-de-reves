"""Signaux de l'application ``dreams``."""

import logging
from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

from dreams.models import Dream

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Dream)
def delete_dream_files(sender: type[Dream], instance: Dream, **kwargs: Any) -> None:
    """Supprime l'audio et l'image du stockage quand un rêve est supprimé.

    Django ne supprime jamais les fichiers liés à un modèle. Sans ce signal,
    les enregistrements vocaux (données personnelles) resteraient sur le disque
    après la suppression du rêve ou du compte, contrairement au droit à
    l'effacement du RGPD. Le signal couvre aussi les suppressions en masse
    (queryset, cascade lors de la suppression d'un utilisateur).

    Une erreur de stockage est journalisée sans bloquer la suppression.

    Args:
        sender: Classe du modèle supprimé.
        instance: Rêve qui vient d'être supprimé.
        **kwargs: Arguments supplémentaires du signal.
    """
    for field in (instance.audio, instance.image):
        if not field:
            continue
        try:
            field.storage.delete(field.name)
        except OSError:
            logger.exception(
                "Impossible de supprimer le fichier %s du rêve %s", field.name, instance.pk
            )
