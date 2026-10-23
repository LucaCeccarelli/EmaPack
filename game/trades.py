from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .friends import are_friends
from .models import Card, Pull, Trade, User


class TradeError(Exception):
    """Can't complete this trade action (message is shown to the user)."""


def _owned(owner, ids):
    """The cards `owner` owns among `ids`, or None if any id is invalid or not owned."""
    # Ids come straight from the form: a tampered, non-numeric one would make the lookup raise.
    if not all(str(i).isdigit() for i in ids):
        return None
    ids = {int(i) for i in ids}
    cards = list(Card.objects.filter(pk__in=ids, pulls__user=owner).distinct())
    return cards if len(cards) == len(ids) else None


def propose_trade(user, friend_username, offered_ids, requested_ids, replaces=None):
    """`user` offers one copy of each `offered_ids` card for one copy of each of the friend's `requested_ids`.

    `replaces`: id of an offer the friend sent `user`; this new one is a counter-offer and supersedes it.
    """
    friend = User.objects.filter(username__iexact=friend_username).first()
    if not friend or not are_friends(user, friend):
        raise TradeError(_("You can only trade with your friends."))
    offered = _owned(user, offered_ids)
    if offered is None:
        raise TradeError(_("You can only offer cards you own."))
    requested = _owned(friend, requested_ids)
    if requested is None:
        raise TradeError(_("%(username)s doesn't own all of those cards.") % {"username": friend.username})
    if not offered and not requested:
        raise TradeError(_("Pick at least one card to give or to receive."))
    with transaction.atomic():  # the counter-offer and the end of the original go together
        if replaces:
            Trade.objects.filter(pk=replaces, from_user=friend, to_user=user).delete()
        trade = Trade.objects.create(from_user=user, to_user=friend)
        trade.offered.set(offered)
        trade.requested.set(requested)
    return trade


def accept_trade(user, trade_id):
    """Move one Pull of each offered card to the recipient and one of each requested card back, then
    delete the offer. Only the recipient can accept. A stale offer (unfriended, or a card no longer owned)
    is deleted and reported instead; the error is raised after the atomic block so that delete isn't rolled back.
    """
    error = None
    with transaction.atomic():
        # Locking the row makes a double-submitted accept wait, then find it gone.
        trade = Trade.objects.select_for_update().filter(pk=trade_id, to_user=user).first()
        if not trade:
            raise TradeError(_("That trade offer no longer exists."))
        offered = set(trade.offered.values_list("pk", flat=True))
        requested = set(trade.requested.values_list("pk", flat=True))
        # Lock every copy of both sides in pk order: a copy can't be traded away twice,
        # and two trades accepted at once lock in the same order (no deadlock).
        pulls = (
            Pull.objects.select_for_update()
            .filter(Q(user=trade.from_user, card__in=offered) | Q(user=user, card__in=requested))
            .order_by("pk")
        )
        moving = {}  # (owner id, card id) -> the one copy that changes hands
        for pull in pulls:
            moving.setdefault((pull.user_id, pull.card_id), pull)
        if not are_friends(trade.from_user, user):
            error = _("You're no longer friends, so this trade was cancelled.")
        elif len(moving) != len(offered) + len(requested):
            error = _("One of the cards is no longer available, so this trade was cancelled.")
        else:
            for pull in moving.values():
                pull.user_id = user.id if pull.user_id == trade.from_user_id else trade.from_user_id
            Pull.objects.bulk_update(moving.values(), ["user"])
        trade.delete()
    if error:
        raise TradeError(error)
    return trade


def remove_trade(user, trade_id):
    """Decline an offer you received or cancel one you sent."""
    deleted, _counts = Trade.objects.filter(pk=trade_id).filter(Q(from_user=user) | Q(to_user=user)).delete()
    if not deleted:
        raise TradeError(_("That trade offer no longer exists."))
