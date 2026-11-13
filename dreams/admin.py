"""Administration des rêves."""

from django.contrib import admin

from dreams.models import Dream


@admin.register(Dream)
class DreamAdmin(admin.ModelAdmin):
    """Vue d'administration des rêves, pour le support et le débogage."""

    list_display = ("id", "user", "status", "emotion", "emotion_score", "created_at")
    list_filter = ("status", "emotion", "created_at")
    search_fields = ("user__username", "transcription")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("user",)
