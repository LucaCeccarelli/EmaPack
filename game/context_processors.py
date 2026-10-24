from django.utils import timezone

from .battles import CHALLENGE_TTL
from .models import Battle


def pending_trades(request):
    """Trade offers waiting for the player's answer, for the badge on the Friends nav link."""
    user = request.user
    return {"incoming_trades": user.trades_received.count() if user.is_authenticated else 0}


def incoming_challenge(request):
    """Drives the nav badge: one cheap query, only for logged-in users."""
    if not request.user.is_authenticated:
        return {}
    return {"incoming_challenge": Battle.objects.filter(
        opponent=request.user, status=Battle.Status.PENDING, created_at__gt=timezone.now() - CHALLENGE_TTL,
    ).exists()}
