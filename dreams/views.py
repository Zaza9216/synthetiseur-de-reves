"""Vues de l'historique des rêves.

Toutes les vues filtrent les rêves sur l'utilisateur connecté : un rêve
appartenant à quelqu'un d'autre renvoie une 404, sans révéler son existence.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.views.generic import DetailView, ListView

from dreams.models import Dream


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
