from django import forms
from django.conf import settings
from django.core.paginator import Paginator
from django.core.validators import MaxLengthValidator
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from . import friends as friend_logic
from .management.commands.import_komi import HEX_COLOR
from .models import Card, Friendship, Rarity, Status, User
from .packs import PackUnavailable, open_pack


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User


MAX_PENDING_PROPOSALS = 3


class ProposalForm(forms.ModelForm):
    # ImageField (Pillow) checks the upload really is an image, whatever its name or content type says.
    logo = forms.ImageField(required=False)
    banner = forms.ImageField(required=False)
    # The player's suggestion; the admin sees it pre-selected and can change it before approving.
    # form="card-editor": the buttons sit under the preview, outside the <form> element.
    rarity = forms.TypedChoiceField(choices=Rarity.choices, coerce=int, required=False, initial=Rarity.COMMON,
                                    widget=forms.RadioSelect(attrs={"form": "card-editor"}))

    class Meta:
        model = Card
        fields = ["name", "tagline", "description", "logo", "banner", "primary_color", "secondary_color", "rarity"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Club Échecs"}),
            "tagline": forms.TextInput(attrs={"placeholder": _("A short line under the name")}),
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": _("Shown on the card's page: what is this club or person about?")}),
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "secondary_color": forms.TextInput(attrs={"type": "color"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Tighter than the model (imported Komi pages can be longer): what fits nicely on a card.
        for name, limit in {"name": 40, "tagline": 90, "description": 2000}.items():
            field = self.fields[name]
            field.max_length = limit
            field.validators.append(MaxLengthValidator(limit))
            field.widget.attrs["maxlength"] = limit
        self.fields["primary_color"].initial = "#3a3f58"
        self.fields["secondary_color"].initial = "#1b1e2e"

    def clean_primary_color(self):
        return self._color("primary_color")

    def clean_secondary_color(self):
        return self._color("secondary_color")

    def _color(self, field):
        value = self.cleaned_data[field]
        if value and not HEX_COLOR.fullmatch(value):  # ends up in an inline style attribute
            raise forms.ValidationError(_("Pick a color like #3a3f58."))
        return value

    def clean_rarity(self):
        return self.cleaned_data["rarity"] or Rarity.COMMON

    def clean_logo(self):
        return self._image("logo")

    def clean_banner(self):
        return self._image("banner")

    def _image(self, field):
        image = self.cleaned_data[field]
        if image and image.size > settings.PROPOSAL_MAX_IMAGE_BYTES:
            max_mb = settings.PROPOSAL_MAX_IMAGE_BYTES // (1024 * 1024)
            raise forms.ValidationError(_("Image too large (max %(max_mb)s MB).") % {"max_mb": max_mb})
        return image


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


COLLECTION_PAGE_SIZE = 24


def _render_collection(request, owned_cards, owner=None):
    """Shared by `collection` and `friend_collection`: search + rarity filter + pagination.

    `owned_cards` is the full (unfiltered) queryset of cards the viewed player owns; its
    unfiltered count drives the discovery progress bar even when a filter narrows the grid.
    """
    q = request.GET.get("q", "").strip()
    rarity = request.GET.get("rarity", "")
    cards = owned_cards
    if q:
        cards = cards.filter(name__icontains=q)
    if rarity.isdigit() and int(rarity) in Rarity.values:
        rarity = int(rarity)
        cards = cards.filter(rarity=rarity)
    else:
        rarity = ""

    page_obj = Paginator(cards, COLLECTION_PAGE_SIZE).get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)

    context = {
        "cards": page_obj,
        "page_obj": page_obj,
        "owned": owned_cards.count(),
        "total": Card.objects.filter(status=Status.APPROVED).count(),
        "q": q,
        "rarity": rarity,
        "rarity_choices": Rarity.choices,
        "extra_qs": params.urlencode(),
    }
    if owner is not None:
        context["owner"] = owner
    return render(request, "game/collection.html", context)


@login_required
def collection(request):
    cards = (
        Card.objects.filter(pulls__user=request.user)
        .annotate(copies=Count("pulls"))  # counts only this user's pulls: filter comes first
        .order_by("-rarity", "name")
    )
    return _render_collection(request, cards)


LEADERBOARD_SIZE = 50


@login_required
def leaderboard(request):
    players = (
        User.objects.annotate(unique=Count("pulls__card", distinct=True), pulled=Count("pulls"))
        .filter(unique__gt=0)
        .order_by("-unique", "-pulled", "username")[:LEADERBOARD_SIZE]
    )
    total = Card.objects.filter(status=Status.APPROVED).count()
    return render(request, "game/leaderboard.html", {"players": players, "total": total})


@login_required
def card_detail(request, pk, username=None):
    owner = request.user
    if username is not None:
        owner = get_object_or_404(User, username__iexact=username)
        if not friend_logic.are_friends(request.user, owner):
            raise Http404
    card = get_object_or_404(Card.objects.filter(pulls__user=owner).distinct(), pk=pk)
    copies = owner.pulls.filter(card=card).count()
    return render(request, "game/card_detail.html", {
        "card": card, "copies": copies, "owner": owner if username is not None else None,
    })


@login_required
def friends(request):
    if request.method == "POST":
        try:
            friend_logic.send_request(request.user, request.POST.get("username", ""))
            messages.success(request, _("Friend request sent!"))
        except friend_logic.FriendError as e:
            messages.error(request, str(e))
        return redirect("friends")
    return render(request, "game/friends.html", {
        "search_min_chars": USERNAME_SEARCH_MIN_CHARS,
        "friends": friend_logic.friends_of(request.user),
        "incoming": Friendship.objects.filter(
            to_user=request.user, status=Friendship.Status.PENDING
        ).select_related("from_user"),
        "outgoing": Friendship.objects.filter(
            from_user=request.user, status=Friendship.Status.PENDING
        ).select_related("to_user"),
    })


USERNAME_SEARCH_MIN_CHARS = 2


@login_required
def friend_search(request):
    """Username suggestions for the add-friend input (prefix match, case-insensitive)."""
    q = request.GET.get("q", "").strip()
    if len(q) < USERNAME_SEARCH_MIN_CHARS:
        return JsonResponse({"usernames": []})
    usernames = (
        User.objects.filter(username__istartswith=q).exclude(pk=request.user.pk)
        .order_by("username").values_list("username", flat=True)[:8]
    )
    return JsonResponse({"usernames": list(usernames)})


@login_required
@require_POST
def friend_accept(request, pk):
    try:
        friend_logic.accept_request(request.user, pk)
    except friend_logic.FriendError as e:
        messages.error(request, str(e))
    return redirect("friends")


@login_required
@require_POST
def friend_remove(request, pk):
    try:
        friend_logic.remove_friendship(request.user, pk)
    except friend_logic.FriendError as e:
        messages.error(request, str(e))
    return redirect("friends")


@login_required
def friend_collection(request, username):
    friend = get_object_or_404(User, username__iexact=username)
    if not friend_logic.are_friends(request.user, friend):
        raise Http404
    cards = (
        Card.objects.filter(pulls__user=friend)
        .annotate(copies=Count("pulls"))
        .order_by("-rarity", "name")
    )
    return _render_collection(request, cards, owner=friend)


@login_required
def propose_card(request):
    mine = request.user.proposals.order_by("-proposed_at")
    at_limit = mine.filter(status=Status.PENDING).count() >= MAX_PENDING_PROPOSALS
    form = ProposalForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and not at_limit and form.is_valid():
        card = form.save(commit=False)
        card.status = Status.PENDING
        card.proposed_by = request.user
        card.proposed_at = timezone.now()
        card.save()
        messages.success(
            request,
            _("“%(name)s” was sent for review. If it's approved, it will show up in packs!") % {"name": card.name},
        )
        return redirect("propose_card")
    # Server preview uses only validated text/colors; images are previewed in the browser (never saved ones).
    data = getattr(form, "cleaned_data", {})
    preview = Card(name=data.get("name") or "Your card", tagline=data.get("tagline", ""),
                   rarity=data.get("rarity") or Rarity.COMMON,
                   primary_color=data.get("primary_color") or "#3a3f58",
                   secondary_color=data.get("secondary_color") or "#1b1e2e")
    return render(request, "game/propose.html", {
        "form": form, "preview": preview, "proposals": mine, "at_limit": at_limit,
        "max_pending": MAX_PENDING_PROPOSALS,
        "max_mb": settings.PROPOSAL_MAX_IMAGE_BYTES // (1024 * 1024),
    })
