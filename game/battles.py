import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .friends import are_friends
from .models import Battle, BattleRound, Card, Rarity, User
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


def scores(battle):
    """(challenger, opponent) points over resolved rounds; a drawn round scores nothing."""
    ch = op = 0
    for r in battle.rounds.filter(challenger_card__isnull=False, opponent_card__isnull=False):
        a = battle.challenger_deck[str(r.challenger_card_id)][r.stat]
        b = battle.opponent_deck[str(r.opponent_card_id)][r.stat]
        ch += a > b
        op += b > a
    return ch, op


def remaining_cards(battle, side):
    """Card ids (strings) in `side`'s snapshot that it hasn't played yet."""
    deck = battle.challenger_deck if side == "challenger" else battle.opponent_deck
    played = {str(pk) for pk in battle.rounds.values_list(f"{side}_card_id", flat=True) if pk}
    return [cid for cid in deck if cid not in played]


def _resolve(battle, rnd, t):
    """Both cards of `rnd` are in: start the next round, or finish if the result is settled."""
    ch, op = scores(battle)
    left = ROUNDS - rnd.number
    if abs(ch - op) > left or left == 0:
        battle.status = Battle.Status.FINISHED
        battle.winner = battle.challenger if ch > op else battle.opponent if op > ch else None
        battle.save()
    else:
        BattleRound.objects.create(
            battle=battle, number=rnd.number + 1, stat=random.choice(STATS), deadline=t + REVEAL_TIME + PICK_TIME,
        )


def advance(battle, now=None):
    """Play out whatever the clock has settled: overdue rounds get random cards for whoever hasn't picked.
    Takes the battle's row lock itself and leaves `battle` fresh.
    """
    now = now or timezone.now()
    with transaction.atomic():
        locked = Battle.objects.select_for_update().get(pk=battle.pk)
        while locked.status == Battle.Status.ACTIVE:
            rnd = locked.rounds.last()
            if rnd.deadline > now:
                break
            if rnd.challenger_card_id is None:
                rnd.challenger_card_id = int(random.choice(remaining_cards(locked, "challenger")))
            if rnd.opponent_card_id is None:
                rnd.opponent_card_id = int(random.choice(remaining_cards(locked, "opponent")))
            rnd.save()
            _resolve(locked, rnd, rnd.deadline)
    battle.refresh_from_db()


def play_card(user, battle_id, card_id, round_number, now=None):
    """Pick a card for the current round; resolves the round once both sides have picked."""
    now = now or timezone.now()
    with transaction.atomic():
        battle = Battle.objects.select_for_update().filter(_mine(user), pk=battle_id).first()
        if not battle:
            raise BattleError(_("This battle is over."))
        advance(battle, now)  # a late pick finds its round already played
        if battle.status != Battle.Status.ACTIVE:
            raise BattleError(_("This battle is over."))
        side = "challenger" if battle.challenger_id == user.pk else "opponent"
        rnd = battle.rounds.last()
        if str(round_number) != str(rnd.number):  # e.g. a late pick whose round advance() just played
            raise BattleError(_("That round is already over."))
        if getattr(rnd, f"{side}_card_id") is not None:
            raise BattleError(_("You already played this round."))
        if str(card_id) not in remaining_cards(battle, side):
            raise BattleError(_("Pick a card from your deck that you haven't played yet."))
        setattr(rnd, f"{side}_card_id", int(card_id))
        rnd.save()
        if rnd.challenger_card_id is not None and rnd.opponent_card_id is not None:
            _resolve(battle, rnd, now)
    return battle


def record(user):
    return Battle.objects.filter(_mine(user), status=Battle.Status.FINISHED).aggregate(
        wins=Count("pk", filter=Q(winner=user)),
        losses=Count("pk", filter=~Q(winner=user) & Q(winner__isnull=False)),
        draws=Count("pk", filter=Q(winner__isnull=True)),
    )


def _live(now):
    """Battles that still occupy their players: active, or pending and not yet expired."""
    return Q(status=Battle.Status.ACTIVE) | Q(status=Battle.Status.PENDING, created_at__gt=now - CHALLENGE_TTL)


def _mine(user):
    return Q(challenger=user) | Q(opponent=user)


def challenge(user, friend_username, now=None):
    """Challenge a friend. Each player can be in at most one pending-or-active battle."""
    now = now or timezone.now()
    friend = User.objects.filter(username=friend_username).first()
    if friend == user:
        raise BattleError(_("You can't challenge yourself."))
    if not friend or not are_friends(user, friend):
        raise BattleError(_("You can only battle your friends."))
    problem = deck_problem(user)
    if problem:
        raise BattleError(problem)
    with transaction.atomic():
        # Locking both players (in pk order) serializes crossing challenges.
        list(User.objects.select_for_update().filter(pk__in=[user.pk, friend.pk]).order_by("pk"))
        # A battle both players abandoned finishes here, so it doesn't keep them busy forever.
        for b in Battle.objects.filter(Q(challenger__in=[user, friend]) | Q(opponent__in=[user, friend]),
                                       status=Battle.Status.ACTIVE):
            advance(b, now)
        if Battle.objects.filter(_mine(user)).filter(_live(now)).exists():
            raise BattleError(_("You're already in a battle."))
        if Battle.objects.filter(_mine(friend)).filter(_live(now)).exists():
            raise BattleError(_("%(username)s is already in a battle.") % {"username": friend.username})
        return Battle.objects.create(challenger=user, opponent=friend, created_at=now)


def _snapshot(user):
    return {
        str(c.pk): {stat: getattr(c, stat) for stat in STATS}
        for c in user.deck.all()
    }


def accept_challenge(user, battle_id, now=None):
    """Freeze both decks and start round 1. A stale challenge (unfriended, or the challenger's deck no
    longer valid) is deleted and reported; the error is raised after the atomic block so that delete sticks.
    """
    now = now or timezone.now()
    error = None
    with transaction.atomic():
        battle = (
            Battle.objects.select_for_update().select_related("challenger")
            .filter(pk=battle_id, opponent=user, status=Battle.Status.PENDING, created_at__gt=now - CHALLENGE_TTL)
            .first()
        )
        if not battle:
            raise BattleError(_("That challenge no longer exists."))
        if not are_friends(battle.challenger, user):
            error = _("You can only battle your friends.")
        elif deck_problem(battle.challenger):
            error = _("%(username)s's deck is no longer valid, so the challenge was cancelled.") % {
                "username": battle.challenger.username,
            }
        if error:
            battle.delete()
        else:
            problem = deck_problem(user)
            if problem:
                raise BattleError(problem)
            battle.challenger_deck = _snapshot(battle.challenger)
            battle.opponent_deck = _snapshot(user)
            battle.status = Battle.Status.ACTIVE
            battle.save()
            BattleRound.objects.create(
                battle=battle, number=1, stat=random.choice(STATS), deadline=now + PICK_TIME,
            )
    if error:
        raise BattleError(error)
    return battle


def remove_challenge(user, battle_id):
    """Decline a challenge you received or cancel one you sent (pending only)."""
    deleted, _counts = Battle.objects.filter(pk=battle_id, status=Battle.Status.PENDING).filter(_mine(user)).delete()
    if not deleted:
        raise BattleError(_("That challenge no longer exists."))


def current_battle(user, now=None):
    """The user's live pending-or-active battle, if any (after settling whatever the clock decided)."""
    now = now or timezone.now()
    for b in Battle.objects.filter(_mine(user), status=Battle.Status.ACTIVE):
        advance(b, now)
    return Battle.objects.filter(_mine(user)).filter(_live(now)).first()


def _outcome(a, b):
    return "win" if a > b else "loss" if a < b else "draw"


def battle_state(user, battle, request=None, now=None):
    """What `user` may see of `battle`. The opponent's unplayed cards (and a pick not yet revealed) never
    enter this dict: only resolved rounds expose both cards.
    """
    if user.pk not in (battle.challenger_id, battle.opponent_id):
        raise BattleError(_("That challenge no longer exists."))
    advance(battle, now)
    me, them = ("challenger", "opponent") if battle.challenger_id == user.pk else ("opponent", "challenger")
    decks = {"challenger": battle.challenger_deck, "opponent": battle.opponent_deck}
    rounds = list(battle.rounds.all())
    resolved = [r for r in rounds if r.challenger_card_id and r.opponent_card_id]
    live = battle.status == Battle.Status.ACTIVE and rounds[-1] if rounds else None
    my_pick = getattr(live, f"{me}_card_id") if live else None

    hand_ids = [int(cid) for cid in remaining_cards(battle, me)] if live else []
    ids = set(hand_ids) | {getattr(r, f"{side}_card_id") for r in resolved for side in (me, them)}
    cards = Card.objects.in_bulk(ids)

    def html(pk):
        return render_to_string("game/_card.html", {"card": cards[pk]}, request)

    def side(r, who):
        pk = getattr(r, f"{who}_card_id")
        return {"id": pk, "html": html(pk), "value": decks[who][str(pk)][r.stat]}

    mine, theirs = scores(battle) if me == "challenger" else scores(battle)[::-1]
    finished = battle.status == Battle.Status.FINISHED
    return {
        "status": battle.status,
        "is_challenger": me == "challenger",
        "opponent": getattr(battle, them).username,
        "score": {"you": mine, "opponent": theirs},
        "round": live and {
            "number": live.number, "stat": live.stat, "deadline": live.deadline.isoformat(),
            "you_picked": my_pick is not None, "opponent_picked": getattr(live, f"{them}_card_id") is not None,
        } or None,
        "hand": [{"id": pk, "html": html(pk)} for pk in hand_ids if pk != my_pick],
        "history": [
            {"number": r.number, "stat": r.stat, "you": side(r, me), "opponent": side(r, them),
             "result": _outcome(decks[me][str(getattr(r, f"{me}_card_id"))][r.stat],
                                decks[them][str(getattr(r, f"{them}_card_id"))][r.stat])}
            for r in resolved
        ],
        "opponent_cards_left": len(decks[them]) - len(resolved) if live else 0,  # an unrevealed pick still counts
        "result": _outcome(mine, theirs) if finished else None,
    }
