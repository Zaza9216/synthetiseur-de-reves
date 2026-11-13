"""Accès protégé aux fichiers des rêves (audio et image).

Les fichiers ne sont jamais servis publiquement : chaque requête vérifie que
le fichier appartient à un rêve de l'utilisateur connecté (ou que celui-ci
est administrateur). Un fichier inaccessible renvoie une 404, sans révéler
son existence.
"""

import mimetypes
import re

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.views.decorators.http import require_GET

from dreams.models import Dream

_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("audio/webm", ".webm")
mimetypes.add_type("audio/mp4", ".m4a")


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Interprète un en-tête ``Range: bytes=début-fin`` (une seule plage).

    Args:
        header: Valeur de l'en-tête ``Range``.
        size: Taille totale du fichier.

    Returns:
        Les bornes incluses ``(début, fin)``, ou ``None`` si l'en-tête est
        absent, invalide ou hors du fichier.
    """
    match = _RANGE_PATTERN.match(header.strip())
    if not match or size == 0:
        return None
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        return None
    if not start_text:  # « bytes=-500 » : les 500 derniers octets
        start, end = max(size - int(end_text), 0), size - 1
    else:
        start = int(start_text)
        end = min(int(end_text), size - 1) if end_text else size - 1
    if start > end or start >= size:
        return None
    return start, end


@login_required
@require_GET
def serve_dream_file(request: HttpRequest, name: str) -> HttpResponse:
    """Sert un fichier de rêve à son propriétaire, avec prise en charge des plages.

    Safari exige les réponses partielles (HTTP 206) pour lire un audio.

    Args:
        request: Requête HTTP entrante.
        name: Chemin du fichier dans le stockage.

    Returns:
        Le fichier (200), une partie du fichier (206), ou une erreur 404 / 416.

    Raises:
        Http404: Si le fichier n'existe pas ou n'appartient pas à l'utilisateur.
    """
    dreams = Dream.objects.filter(Q(audio=name) | Q(image=name))
    if not request.user.is_staff:
        dreams = dreams.filter(user=request.user)
    if not dreams.exists():
        raise Http404("Fichier introuvable.")

    try:
        with default_storage.open(name, "rb") as file:
            data = file.read()
    except FileNotFoundError as error:
        raise Http404("Fichier introuvable.") from error

    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    size = len(data)
    range_header = request.headers.get("Range", "")
    byte_range = _parse_range(range_header, size) if range_header else None

    if range_header and byte_range is None:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    if byte_range:
        start, end = byte_range
        response = HttpResponse(data[start : end + 1], status=206, content_type=content_type)
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    else:
        response = HttpResponse(data, content_type=content_type)
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, max-age=3600"
    return response
