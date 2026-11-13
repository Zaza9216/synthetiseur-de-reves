"""Vues de l'historique des rêves.

Toutes les vues filtrent les rêves sur l'utilisateur connecté : un rêve
appartenant à quelqu'un d'autre renvoie une 404, sans révéler son existence.
"""

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.forms import Form
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DeleteView, DetailView, ListView

from dreams.ai.budget import BUDGET_EXCEEDED_MESSAGE, is_budget_exceeded
from dreams.forms import DreamCreateForm, DreamFilterForm
from dreams.models import Dream, Status
from dreams.pipeline import enqueue_dream, retry_dream
from dreams.quotas import dreams_left_today
from dreams.stats import compute_dashboard_stats, resolve_period

logger = logging.getLogger(__name__)


class UserDreamsMixin(LoginRequiredMixin):
    """Restreint les vues aux rêves de l'utilisateur connecté."""

    model = Dream

    def get_queryset(self) -> QuerySet[Dream]:
        """Retourne uniquement les rêves de l'utilisateur connecté."""
        return Dream.objects.filter(user=self.request.user)


class DreamListView(UserDreamsMixin, ListView):
    """Tableau de bord : statistiques de la période et historique filtrable des rêves.

    Les statistiques portent sur la période choisie (toutes émotions), pour que
    la répartition reste lisible ; la grille des rêves applique aussi le filtre
    d'émotion.
    """

    template_name = "dreams/dream_list.html"
    context_object_name = "dreams"
    paginate_by = 9

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Valide les filtres avant de construire la page."""
        self.filter_form = DreamFilterForm(request.GET or None)
        filters = self.filter_form.cleaned_data if self.filter_form.is_valid() else {}
        self.period = resolve_period(filters.get("start"), filters.get("end"))
        self.emotion = filters.get("emotion", "")
        return super().get(request, *args, **kwargs)

    def period_queryset(self) -> QuerySet[Dream]:
        """Rêves de l'utilisateur sur la période choisie."""
        start, end = self.period
        return super().get_queryset().filter(created_at__date__gte=start, created_at__date__lte=end)

    def get_queryset(self) -> QuerySet[Dream]:
        """Rêves de la période, filtrés par émotion si demandé."""
        dreams = self.period_queryset()
        if self.emotion:
            dreams = dreams.filter(emotion=self.emotion)
        return dreams

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Ajoute le formulaire de filtres, la période et les statistiques."""
        context = super().get_context_data(**kwargs)
        start, end = self.period
        today = timezone.localdate()
        context.update(
            filter_form=self.filter_form,
            period_start=start,
            period_end=end,
            emotion_filter=self.emotion,
            stats=compute_dashboard_stats(self.period_queryset(), start, end),
            has_any_dream=Dream.objects.filter(user=self.request.user).exists(),
            presets=[
                ("7 jours", today - timedelta(days=6)),
                ("30 jours", today - timedelta(days=29)),
                ("12 semaines", today - timedelta(days=83)),
                ("12 mois", today - timedelta(days=364)),
            ],
            today=today,
        )
        return context


class DreamDetailView(UserDreamsMixin, DetailView):
    """Détail d'un rêve : image, transcription, émotion, audio et suivi du traitement."""

    template_name = "dreams/dream_detail.html"
    context_object_name = "dream"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Ajoute les étapes de progression du traitement."""
        context = super().get_context_data(**kwargs)
        statuses = [status for status, _ in PROGRESS_STEPS]
        current = statuses.index(self.object.status) if self.object.status in statuses else -1
        context["progress_steps"] = [
            {
                "label": label,
                "state": "done" if i < current else "active" if i == current else "todo",
            }
            for i, (_, label) in enumerate(PROGRESS_STEPS)
        ]
        return context


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

        if is_budget_exceeded():
            if _wants_json(request):
                return JsonResponse({"errors": [BUDGET_EXCEEDED_MESSAGE]}, status=503)
            messages.warning(request, BUDGET_EXCEEDED_MESSAGE)
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
        enqueue_dream(dream.pk)

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


# Étapes affichées à l'utilisateur pendant le traitement, dans l'ordre.
PROGRESS_STEPS: tuple[tuple[Status, str], ...] = (
    (Status.TRANSCRIPTION, "Transcription"),
    (Status.ANALYSE, "Émotion"),
    (Status.GENERATION, "Image"),
)


def dream_status_payload(dream: Dream) -> dict[str, Any]:
    """Construit l'état de traitement d'un rêve, pour la page de suivi.

    Args:
        dream: Le rêve concerné.

    Returns:
        Un dictionnaire sérialisable en JSON : statut, libellé, indicateurs.
    """
    return {
        "status": dream.status,
        "status_label": dream.get_status_display(),
        "is_processing": dream.is_processing,
        "can_retry": dream.can_retry,
        "error_message": dream.error_message,
    }


@require_GET
def dream_status(request: HttpRequest, pk: int) -> JsonResponse:
    """Renvoie l'état du traitement d'un rêve (interrogé régulièrement par la page).

    Args:
        request: Requête HTTP entrante.
        pk: Identifiant du rêve.

    Returns:
        L'état du traitement en JSON, ou 401 / 404.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentification requise."}, status=401)
    dream = get_object_or_404(Dream, pk=pk, user=request.user)
    return JsonResponse(dream_status_payload(dream))


@login_required
@require_POST
def dream_retry(request: HttpRequest, pk: int) -> HttpResponse:
    """Relance le traitement d'un rêve en échec ou bloqué.

    Args:
        request: Requête HTTP entrante.
        pk: Identifiant du rêve.

    Returns:
        Une redirection vers la page du rêve.
    """
    dream = get_object_or_404(Dream, pk=pk, user=request.user)
    if retry_dream(dream):
        messages.info(request, "Le traitement de votre rêve a été relancé.")
    else:
        messages.warning(request, "Ce rêve ne peut pas être relancé pour le moment.")
    return redirect("dreams:detail", pk=dream.pk)
