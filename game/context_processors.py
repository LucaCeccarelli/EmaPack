from django.utils import timezone

from .battles import CHALLENGE_TTL
from .models import Battle


def incoming_challenge(request):
    """Drives the nav badge: one cheap query, only for logged-in users."""
    if not request.user.is_authenticated:
        return {}
    return {"incoming_challenge": Battle.objects.filter(
        opponent=request.user, status=Battle.Status.PENDING, created_at__gt=timezone.now() - CHALLENGE_TTL,
    ).exists()}
