"""Routes de l'application ``dreams``."""

from django.urls import path

from dreams import views

app_name = "dreams"

urlpatterns = [
    path("", views.DreamListView.as_view(), name="list"),
    path("<int:pk>/", views.DreamDetailView.as_view(), name="detail"),
    path("<int:pk>/supprimer/", views.DreamDeleteView.as_view(), name="delete"),
]
