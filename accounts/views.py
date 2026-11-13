"""Vues de l'application ``accounts``."""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from accounts.forms import SignUpForm

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
        login(request, user)
        logger.info("Nouvel utilisateur inscrit (id=%s)", user.pk)
        messages.success(request, f"Bienvenue {user.username} ! Votre compte est créé.")
        return redirect(settings.LOGIN_REDIRECT_URL)

    return render(request, "registration/signup.html", {"form": form})
