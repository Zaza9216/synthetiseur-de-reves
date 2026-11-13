"""Routes de l'application ``dreams``."""

from django.urls import path

from dreams import views

app_name = "dreams"

urlpatterns = [
    path("", views.DreamListView.as_view(), name="list"),
    path("nouveau/", views.DreamCreateView.as_view(), name="create"),
    path("<int:pk>/", views.DreamDetailView.as_view(), name="detail"),
    path("<int:pk>/supprimer/", views.DreamDeleteView.as_view(), name="delete"),
    path("<int:pk>/statut/", views.dream_status, name="status"),
    path("<int:pk>/relancer/", views.dream_retry, name="retry"),
]
