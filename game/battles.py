from datetime import timedelta

from django.utils.translation import gettext_lazy as _

from .models import Rarity
from .trades import _owned

DECK_SIZE = 5
ROUNDS = 5
RARITY_CAP = {Rarity.LEGENDARY: 1, Rarity.EPIC: 2}
PICK_TIME = timedelta(seconds=30)
REVEAL_TIME = timedelta(seconds=3)
CHALLENGE_TTL = timedelta(minutes=2)
STATS = ("subscriber_count", "post_count", "event_count")


class BattleError(Exception):
    """Can't complete this battle action (message is shown to the user)."""


def _cards_problem(cards):
    """The first rule these (distinct) cards break as a deck, or None."""
    if len(cards) != DECK_SIZE:
        return _("A deck needs exactly %(size)s different cards.") % {"size": DECK_SIZE}
    for rarity, cap in RARITY_CAP.items():
        if sum(c.rarity == rarity for c in cards) > cap:
            return _("At most %(count)s %(rarity)s card(s) per deck.") % {
                "count": cap, "rarity": Rarity(rarity).label,
            }
    return None


def deck_problem(user):
    """Why `user`'s saved deck can't be used right now (size, no longer owned, rarity cap), or None."""
    cards = list(user.deck.all())
    if len(cards) == DECK_SIZE and _owned(user, [c.pk for c in cards]) is None:
        return _("You can only use cards you own.")
    return _cards_problem(cards)


def save_deck(user, card_ids):
    cards = _owned(user, set(card_ids))
    if cards is None:
        raise BattleError(_("You can only use cards you own."))
    problem = _cards_problem(cards)
    if problem:
        raise BattleError(problem)
    user.deck.set(cards)
