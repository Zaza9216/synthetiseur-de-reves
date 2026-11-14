"""Vues de l'application ``accounts``."""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.export import build_user_export
from accounts.forms import DeleteAccountForm, SignUpForm
from dreams.models import Dream

logger = logging.getLogger(__name__)


def signup(request: HttpRequest) -> HttpResponse:
    """Inscrit un nouvel utilisateur puis le connecte directement.

    Args:
        request: Requête HTTP entrante.

    Returns:
        Le formulaire d'inscription (GET ou erreurs de saisie), ou une
        redirection vers l'espace personnel après inscription réussie.
    """
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="accounts.backends.CaseInsensitiveModelBackend")
        logger.info("Nouvel utilisateur inscrit (id=%s)", user.pk)
        messages.success(request, f"Bienvenue {user.username} ! Votre compte est créé.")
        return redirect(settings.LOGIN_REDIRECT_URL)

    return render(request, "registration/signup.html", {"form": form})


@login_required
def my_data(request: HttpRequest) -> HttpResponse:
    """Espace « Mes données » : résumé, export et suppression du compte.

    Args:
        request: Requête HTTP entrante.

    Returns:
        La page, ou une redirection vers l'accueil après suppression du compte.
    """
    form = DeleteAccountForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user_id = request.user.pk
        user = request.user
        logout(request)
        user.delete()  # supprime aussi les rêves et leurs fichiers (cascade + signal)
        logger.info("Compte %s supprimé à la demande de l'utilisateur", user_id)
        messages.success(request, "Votre compte et toutes vos données ont été supprimés.")
        return redirect("core:home")

    dreams = Dream.objects.filter(user=request.user)
    context = {
        "form": form,
        "dream_count": dreams.count(),
        "audio_count": dreams.exclude(audio="").count(),
        "image_count": dreams.exclude(image="").count(),
    }
    return render(request, "accounts/my_data.html", context)


@login_required
@require_GET
def export_data(request: HttpRequest) -> FileResponse:
    """Télécharge l'archive ZIP de toutes les données de l'utilisateur.

    Args:
        request: Requête HTTP entrante.

    Returns:
        L'archive en pièce jointe.
    """
    archive = build_user_export(request.user)
    filename = f"mes-reves-{timezone.localdate():%Y-%m-%d}.zip"
    logger.info("Export des données de l'utilisateur %s", request.user.pk)
    return FileResponse(
        archive, as_attachment=True, filename=filename, content_type="application/zip"
    )
