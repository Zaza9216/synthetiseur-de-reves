"""Export de toutes les données d'un utilisateur (droit à la portabilité, RGPD art. 20)."""

import json
import zipfile
from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile
from typing import IO, Any

from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from dreams.models import Dream

README = """Synthétiseur de rêves : export de vos données
===============================================

Ce fichier contient toutes les données associées à votre compte :

- donnees.json  : votre compte et vos rêves (récit, émotion, dates, statut…),
                  dans un format ouvert et lisible par d'autres logiciels ;
- audio/        : vos enregistrements vocaux ;
- images/       : les illustrations générées pour vos rêves.

Export réalisé le {date}.
"""

# Au-delà, l'archive en cours de construction passe de la mémoire à un fichier temporaire.
_MEMORY_LIMIT = 10 * 1024 * 1024


def _dream_record(dream: Dream, audio_path: str | None, image_path: str | None) -> dict[str, Any]:
    return {
        "id": dream.pk,
        "cree_le": dream.created_at.isoformat(),
        "traite_le": dream.processed_at.isoformat() if dream.processed_at else None,
        "statut": dream.get_status_display(),
        "recit": dream.transcription,
        "emotion": dream.get_emotion_display() if dream.emotion else None,
        "confiance_emotion": dream.emotion_score,
        "methode_analyse": dream.get_emotion_method_display() if dream.emotion_method else None,
        "duree_audio_secondes": dream.audio_duration,
        "prompt_image": dream.image_prompt or None,
        "fichier_audio": audio_path,
        "fichier_image": image_path,
    }


def _add_file(archive: zipfile.ZipFile, field: Any, folder: str, dream_id: int) -> str | None:
    """Copie un fichier du stockage dans l'archive ; renvoie son chemin, ou None."""
    if not field:
        return None
    path = f"{folder}/reve-{dream_id}{PurePosixPath(field.name).suffix}"
    try:
        with field.open("rb") as source:
            archive.writestr(path, source.read())
    except FileNotFoundError:
        return None
    return path


def build_user_export(user: AbstractBaseUser) -> IO[bytes]:
    """Construit l'archive ZIP des données d'un utilisateur.

    Args:
        user: L'utilisateur dont on exporte les données.

    Returns:
        Un fichier temporaire contenant l'archive, positionné au début.
    """
    buffer = SpooledTemporaryFile(max_size=_MEMORY_LIMIT)  # noqa: SIM115 - renvoyé à l'appelant
    now = timezone.localtime()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        dreams = []
        for dream in Dream.objects.filter(user=user).order_by("created_at"):
            audio = _add_file(archive, dream.audio, "audio", dream.pk)
            image = _add_file(archive, dream.image, "images", dream.pk)
            dreams.append(_dream_record(dream, audio, image))
        data = {
            "export_genere_le": now.isoformat(),
            "compte": {
                "identifiant": user.get_username(),
                "email": user.email,
                "inscrit_le": user.date_joined.isoformat(),
                "derniere_connexion": user.last_login.isoformat() if user.last_login else None,
            },
            "nombre_de_reves": len(dreams),
            "reves": dreams,
        }
        archive.writestr("donnees.json", json.dumps(data, ensure_ascii=False, indent=2))
        archive.writestr("LISEZMOI.txt", README.format(date=now.strftime("%d/%m/%Y à %H:%M")))
    buffer.seek(0)
    return buffer
