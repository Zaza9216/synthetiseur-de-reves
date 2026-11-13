"""Validation des fichiers audio envoyés par les utilisateurs.

On ne fait pas confiance au nom ni au type MIME annoncés par le navigateur :
le format est vérifié à partir des premiers octets du fichier (« signature »).
Un fichier texte ou un exécutable renommé en ``.mp3`` est ainsi refusé avant
d'être stocké ou envoyé à l'API de transcription.
"""

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

# Formats acceptés par l'API de transcription d'OpenAI.
ALLOWED_EXTENSIONS = frozenset(
    {"webm", "ogg", "oga", "mp3", "mpeg", "mpga", "mp4", "m4a", "wav", "flac"}
)

_HEADER_SIZE = 16


def detect_audio_format(header: bytes) -> str | None:
    """Identifie le conteneur audio à partir des premiers octets du fichier.

    Args:
        header: Les premiers octets du fichier (au moins 12).

    Returns:
        Le nom du format (``"webm"``, ``"ogg"``, ``"wav"``, ``"mp3"``,
        ``"mp4"``, ``"flac"``) ou ``None`` s'il n'est pas reconnu.
    """
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"  # conteneur Matroska / WebM
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"fLaC"):
        return "flac"
    if header[4:8] == b"ftyp":
        return "mp4"  # MP4 / M4A
    if header.startswith(b"ID3") or (
        len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
    ):
        return "mp3"  # balise ID3 ou trame MPEG
    return None


def validate_audio_file(file: UploadedFile) -> None:
    """Vérifie qu'un fichier envoyé est un enregistrement audio acceptable.

    Contrôles effectués : fichier non vide, taille maximale, extension
    autorisée, et contenu réellement audio (signature des premiers octets).

    Args:
        file: Le fichier envoyé par l'utilisateur.

    Raises:
        ValidationError: Si l'un des contrôles échoue, avec un message
            compréhensible par l'utilisateur.
    """
    max_bytes = settings.DREAM_AUDIO_MAX_MB * 1024 * 1024
    if file.size == 0:
        raise ValidationError("Le fichier audio est vide.", code="empty")
    if file.size > max_bytes:
        raise ValidationError(
            f"Le fichier est trop volumineux (maximum {settings.DREAM_AUDIO_MAX_MB} Mo).",
            code="too_large",
        )

    extension = Path(file.name or "").suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValidationError(
            f"Format non pris en charge. Formats acceptés : {allowed}.", code="bad_extension"
        )

    file.seek(0)
    header = file.read(_HEADER_SIZE)
    file.seek(0)
    if detect_audio_format(header) is None:
        raise ValidationError(
            "Ce fichier ne semble pas être un enregistrement audio valide.", code="not_audio"
        )
