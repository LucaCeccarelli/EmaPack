import mimetypes

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve

from game import views

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
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
    path("friends/<str:username>/trade/", views.trade_new, name="trade_new"),
    path("trades/<int:pk>/accept/", views.trade_accept, name="trade_accept"),
    path("trades/<int:pk>/remove/", views.trade_remove, name="trade_remove"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
]

# Always served, not just when DEBUG: there is no separate media server
# (nginx/S3/...) in front of this app, so Django has to serve card images
# itself in every environment. Not via the `static()` helper: it silently
# returns no route when DEBUG=False.
# Python < 3.13 doesn't know .webp, and the slim image has no /etc/mime.types:
# without this, ~2k Komi images go out as application/octet-stream, which
# browsers refuse to render (SecurityMiddleware sends nosniff).
mimetypes.add_type("image/webp", ".webp")
urlpatterns += [
    re_path(rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
