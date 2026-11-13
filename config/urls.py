"""Routes principales du projet."""

from django.contrib import admin
from django.urls import include, path

from dreams.media import serve_dream_file

urlpatterns = [
    path("admin/", admin.site.urls),
    path("comptes/", include("accounts.urls")),
    path("reves/", include("dreams.urls")),
    # Fichiers des rêves : jamais publics, servis après contrôle d'accès.
    path("fichiers/<path:name>", serve_dream_file, name="dream_file"),
    path("", include("core.urls")),
]
