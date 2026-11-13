"""Administration des rêves."""

from django.contrib import admin
from django.http import HttpRequest

from dreams.models import ApiCall, Dream


@admin.register(Dream)
class DreamAdmin(admin.ModelAdmin):
    """Vue d'administration des rêves, pour le support et le débogage."""

    list_display = ("id", "user", "status", "emotion", "emotion_score", "created_at")
    list_filter = ("status", "emotion", "created_at")
    search_fields = ("user__username", "transcription")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("user",)


@admin.register(ApiCall)
class ApiCallAdmin(admin.ModelAdmin):
    """Journal des appels aux API d'IA : latence, échecs, coût."""

    list_display = (
        "created_at",
        "service",
        "model_name",
        "success",
        "duration_ms",
        "cost_usd",
        "error_type",
        "dream",
    )
    list_filter = ("service", "success", "model_name", "created_at")
    readonly_fields = [field.name for field in ApiCall._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Le journal est alimenté uniquement par l'application."""
        return False
