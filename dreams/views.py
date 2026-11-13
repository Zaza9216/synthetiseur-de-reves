"""Vues de l'historique des rêves.

Toutes les vues filtrent les rêves sur l'utilisateur connecté : un rêve
appartenant à quelqu'un d'autre renvoie une 404, sans révéler son existence.
"""

import logging
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.forms import Form
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DeleteView, DetailView, ListView

from dreams.forms import DreamCreateForm
from dreams.models import Dream
from dreams.quotas import dreams_left_today

logger = logging.getLogger(__name__)


class UserDreamsMixin(LoginRequiredMixin):
    """Restreint les vues aux rêves de l'utilisateur connecté."""

    model = Dream

    def get_queryset(self) -> QuerySet[Dream]:
        """Retourne uniquement les rêves de l'utilisateur connecté."""
        return Dream.objects.filter(user=self.request.user)


class DreamListView(UserDreamsMixin, ListView):
    """Historique paginé des rêves de l'utilisateur, du plus récent au plus ancien."""

    template_name = "dreams/dream_list.html"
    context_object_name = "dreams"
    paginate_by = 9


class DreamDetailView(UserDreamsMixin, DetailView):
    """Détail d'un rêve : image, transcription, émotion, audio."""

    template_name = "dreams/dream_detail.html"
    context_object_name = "dream"


class DreamDeleteView(UserDreamsMixin, DeleteView):
    """Suppression définitive d'un rêve et de ses fichiers, après confirmation.

    GET affiche la page de confirmation ; POST supprime. Les fichiers sont
    effacés par le signal ``post_delete`` (voir ``dreams/signals.py``).
    """

    template_name = "dreams/dream_confirm_delete.html"
    context_object_name = "dream"
    success_url = reverse_lazy("dreams:list")

    def form_valid(self, form: Form) -> HttpResponse:
        """Supprime le rêve, journalise l'action et confirme à l'utilisateur."""
        dream_id = self.object.pk
        response = super().form_valid(form)
        logger.info("Rêve %s supprimé par l'utilisateur %s", dream_id, self.request.user.pk)
        messages.success(self.request, "Le rêve et ses fichiers ont été supprimés définitivement.")
        return response


def _wants_json(request: HttpRequest) -> bool:
    """Indique si la requête vient du script d'enregistrement (réponse JSON attendue)."""
    return "application/json" in request.headers.get("Accept", "")


class DreamCreateView(LoginRequiredMixin, View):
    """Création d'un rêve à partir d'un enregistrement ou d'un fichier audio.

    Deux modes d'envoi partagent la même vue :

    - le script d'enregistrement envoie l'audio en ``fetch`` et attend du JSON ;
    - le formulaire classique (sans JavaScript) attend une redirection ou la
      page avec les erreurs.
    """

    template_name = "dreams/dream_create.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Affiche la page d'enregistrement d'un nouveau rêve."""
        return self._render(request, DreamCreateForm())

    def post(self, request: HttpRequest) -> HttpResponse:
        """Valide l'audio, crée le rêve et redirige vers sa page de suivi."""
        if dreams_left_today(request.user) == 0:
            error = "Vous avez atteint la limite de rêves pour aujourd'hui. Revenez demain !"
            logger.warning("Quota journalier atteint pour l'utilisateur %s", request.user.pk)
            if _wants_json(request):
                return JsonResponse({"errors": [error]}, status=429)
            messages.warning(request, error)
            return redirect("dreams:list")

        form = DreamCreateForm(request.POST, request.FILES)
        if not form.is_valid():
            if _wants_json(request):
                errors = [str(e) for field_errors in form.errors.values() for e in field_errors]
                return JsonResponse({"errors": errors}, status=400)
            return self._render(request, form, status=400)

        dream = form.save(commit=False)
        dream.user = request.user
        dream.save()
        logger.info("Rêve %s créé par l'utilisateur %s", dream.pk, request.user.pk)

        detail_url = reverse("dreams:detail", args=[dream.pk])
        if _wants_json(request):
            return JsonResponse({"id": dream.pk, "redirect_url": detail_url}, status=201)
        return redirect(detail_url)

    def _render(
        self, request: HttpRequest, form: DreamCreateForm, status: int = 200
    ) -> HttpResponse:
        """Affiche la page de création avec le formulaire et le quota restant."""
        context: dict[str, Any] = {
            "form": form,
            "dreams_left": dreams_left_today(request.user),
            "max_seconds": settings.DREAM_AUDIO_MAX_SECONDS,
            "max_mb": settings.DREAM_AUDIO_MAX_MB,
        }
        return render(request, self.template_name, context, status=status)
