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
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("cards/<int:pk>/", views.card_detail, name="card_detail"),
    path("cards/propose/", views.propose_card, name="propose_card"),
    path("friends/", views.friends, name="friends"),
    path("friends/search/", views.friend_search, name="friend_search"),
    path("friends/<int:pk>/accept/", views.friend_accept, name="friend_accept"),
    path("friends/<int:pk>/remove/", views.friend_remove, name="friend_remove"),
    path("friends/<str:username>/collection/", views.friend_collection, name="friend_collection"),
    path("friends/<str:username>/cards/<int:pk>/", views.card_detail, name="friend_card_detail"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)  # only active when DEBUG
