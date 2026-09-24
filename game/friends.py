from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .models import Friendship, User


class FriendError(Exception):
    """Can't complete this friend action (message is shown to the user)."""


def are_friends(a, b):
    return (
        Friendship.objects.filter(status=Friendship.Status.ACCEPTED)
        .filter(Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a))
        .exists()
    )


def friends_of(user):
    """Accepted friends of `user`, as User instances (each tagged with its friendship_id)."""
    rows = (
        Friendship.objects.filter(status=Friendship.Status.ACCEPTED)
        .filter(Q(from_user=user) | Q(to_user=user))
        .select_related("from_user", "to_user")
    )
    friends = []
    for row in rows:
        other = row.to_user if row.from_user_id == user.id else row.from_user
        other.friendship_id = row.pk
        friends.append(other)
    return friends


def send_request(user, username):
    """Send a friend request from `user` to `username` (case-insensitive); auto-accepts a crossed request."""
    username = (username or "").strip()
    try:
        target = User.objects.get(username__iexact=username)
    except User.DoesNotExist:
        raise FriendError(_("No player named “%(username)s”.") % {"username": username})
    if target.pk == user.pk:
        raise FriendError(_("You can't add yourself."))
    if are_friends(user, target):
        raise FriendError(_("You're already friends with %(username)s.") % {"username": target.username})
    reverse_request = Friendship.objects.filter(
        from_user=target, to_user=user, status=Friendship.Status.PENDING
    ).first()
    if reverse_request:
        reverse_request.status = Friendship.Status.ACCEPTED
        reverse_request.save(update_fields=["status"])
        return reverse_request
    friendship, created = Friendship.objects.get_or_create(from_user=user, to_user=target)
    if not created:
        raise FriendError(_("You already sent %(username)s a request.") % {"username": target.username})
    return friendship


def accept_request(user, friendship_id):
    friendship = Friendship.objects.filter(
        pk=friendship_id, to_user=user, status=Friendship.Status.PENDING
    ).first()
    if not friendship:
        raise FriendError(_("That request no longer exists."))
    friendship.status = Friendship.Status.ACCEPTED
    friendship.save(update_fields=["status"])
    return friendship


def remove_friendship(user, friendship_id):
    """Decline a request, cancel one you sent, or remove an accepted friend — all just delete the row."""
    deleted, _counts = Friendship.objects.filter(pk=friendship_id).filter(Q(from_user=user) | Q(to_user=user)).delete()
    if not deleted:
        raise FriendError(_("That request no longer exists."))
