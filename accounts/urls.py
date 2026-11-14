"""Routes de l'application ``accounts``."""

from django.contrib.auth import views as auth_views
from django.urls import path

from accounts import views
from accounts.forms import LoginForm

app_name = "accounts"

urlpatterns = [
    path("inscription/", views.signup, name="signup"),
    path(
        "connexion/",
        auth_views.LoginView.as_view(
            redirect_authenticated_user=True, authentication_form=LoginForm
        ),
        name="login",
    ),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("mes-donnees/", views.my_data, name="my_data"),
    path("mes-donnees/export.zip", views.export_data, name="export"),
]
