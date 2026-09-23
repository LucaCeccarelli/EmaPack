from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from .models import Card, User
from .packs import PackUnavailable, open_pack


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User


def iso(dt):
    return dt.isoformat() if dt else None


def signup(request):
    form = SignupForm(request.POST or None)
    if form.is_valid():
        login(request, form.save())
        return redirect("home")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def home(request):
    return render(request, "game/home.html", {"next_pack_at": iso(request.user.next_pack_at)})


@login_required
@require_POST
def open_pack_view(request):
    owned_before = set(request.user.pulls.values_list("card_id", flat=True))
    try:
        cards = open_pack(request.user)
    except PackUnavailable as e:
        request.user.refresh_from_db(fields=["next_pack_at"])
        return JsonResponse({"error": str(e), "next_pack_at": iso(request.user.next_pack_at)}, status=409)
    return JsonResponse({
        "next_pack_at": iso(request.user.next_pack_at),
        "cards": [
            {
                "rarity": card.rarity,
                "slug": card.rarity_slug,
                "is_new": card.id not in owned_before,
                "html": render_to_string("game/_card.html", {"card": card}, request),
            }
            for card in cards
        ],
    })


@login_required
def collection(request):
    cards = (
        Card.objects.filter(pulls__user=request.user)
        .annotate(copies=Count("pulls"))  # counts only this user's pulls: filter comes first
        .order_by("-rarity", "name")
    )
    return render(request, "game/collection.html", {"cards": cards, "total": Card.objects.count()})


@login_required
def card_detail(request, pk):
    card = get_object_or_404(Card.objects.filter(pulls__user=request.user).distinct(), pk=pk)
    copies = request.user.pulls.filter(card=card).count()
    return render(request, "game/card_detail.html", {"card": card, "copies": copies})
