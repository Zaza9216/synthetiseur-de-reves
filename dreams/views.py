"""Vues de l'historique des rêves.

Toutes les vues filtrent les rêves sur l'utilisateur connecté : un rêve
appartenant à quelqu'un d'autre renvoie une 404, sans révéler son existence.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.forms import Form
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView

from dreams.models import Dream

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
