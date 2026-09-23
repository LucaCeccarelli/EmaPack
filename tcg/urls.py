from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from game import views

urlpatterns = [
    path("", views.home, name="home"),
    path("packs/open/", views.open_pack_view, name="open_pack"),
    path("collection/", views.collection, name="collection"),
    path("cards/<int:pk>/", views.card_detail, name="card_detail"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)  # only active when DEBUG
