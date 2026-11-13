"""Routes de l'application ``core``."""

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("supervision/", views.supervision, name="supervision"),
]
