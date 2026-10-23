from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .friends import are_friends
from .models import Card, Pull, Trade, User


class TradeError(Exception):
    """Can't complete this trade action (message is shown to the user)."""


def propose_trade(user, friend_username, requested_id, offered_ids):
    """`user` offers one copy of each card in `offered_ids` for one of the friend's copies of `requested_id`."""
    friend = User.objects.filter(username__iexact=friend_username).first()
    if not friend or not are_friends(user, friend):
        raise TradeError(_("You can only trade with your friends."))
    requested = Card.objects.filter(pk=requested_id, pulls__user=friend).first()
    if not requested:
        raise TradeError(_("%(username)s doesn't own that card.") % {"username": friend.username})
    # Ids come straight from the form: a tampered, non-numeric one would make the lookup raise.
    offered_ids = {int(i) for i in offered_ids if str(i).isdigit()}
    offered = list(Card.objects.filter(pk__in=offered_ids, pulls__user=user).distinct())
    if not offered or len(offered) != len(offered_ids):
        raise TradeError(_("Pick cards you own to offer."))
    trade = Trade.objects.create(from_user=user, to_user=friend, requested=requested)
    trade.offered.set(offered)
    return trade


def accept_trade(user, trade_id):
    """Move one Pull of each offered card to the recipient and one of `requested` back, then delete the offer.

    Only the recipient can accept. A stale offer (unfriended, or a card no longer owned) is deleted and reported instead;
    the error is raised after the atomic block so that delete isn't rolled back.
    """
    error = None
    with transaction.atomic():
        # Locking the row makes a double-submitted accept wait, then find it gone.
        trade = Trade.objects.select_for_update().filter(pk=trade_id, to_user=user).first()
        if not trade:
            raise TradeError(_("That trade offer no longer exists."))
        offered_ids = set(trade.offered.values_list("pk", flat=True))
        # Lock every copy of both sides in pk order: a copy can't be swapped away twice,
        # and two trades accepted at once lock in the same order (no deadlock).
        pulls = (
            Pull.objects.select_for_update()
            .filter(Q(user=trade.from_user, card__in=offered_ids) | Q(user=user, card=trade.requested))
            .order_by("pk")
        )
        given = {}  # card id -> one of from_user's copies
        received = None
        for pull in pulls:
            if pull.user_id == trade.from_user_id:
                given.setdefault(pull.card_id, pull)
            elif received is None:
                received = pull
        if not are_friends(trade.from_user, user):
            error = _("You're no longer friends, so this trade was cancelled.")
        elif given.keys() != offered_ids or not received:
            error = _("One of the cards is no longer available, so this trade was cancelled.")
        else:
            for pull in given.values():
                pull.user = user
            received.user = trade.from_user
            Pull.objects.bulk_update([*given.values(), received], ["user"])
        trade.delete()
    if error:
        raise TradeError(error)
    return trade


def remove_trade(user, trade_id):
    """Decline an offer you received or cancel one you sent."""
    deleted, _counts = Trade.objects.filter(pk=trade_id).filter(Q(from_user=user) | Q(to_user=user)).delete()
    if not deleted:
        raise TradeError(_("That trade offer no longer exists."))
