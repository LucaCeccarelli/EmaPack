from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    # None = never opened a pack, so one is available right away.
    next_pack_at = models.DateTimeField(null=True, blank=True)


class Rarity(models.IntegerChoices):
    COMMON = 1, _("Common")
    UNCOMMON = 2, _("Uncommon")
    RARE = 3, _("Rare")
    EPIC = 4, _("Epic")
    LEGENDARY = 5, _("Legendary")


class Status(models.TextChoices):
    PENDING = "pending", _("Pending review")
    APPROVED = "approved", _("Approved")
    REJECTED = "rejected", _("Rejected")


class Card(models.Model):
    """A collectible card: one Komi page (a club or a member), or a card proposed by a player."""

    komi_id = models.UUIDField(unique=True, null=True, blank=True)  # None for player-proposed cards
    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=500, blank=True)  # the page's short description line
    description = models.TextField(blank=True)  # text of the page's presentation blocks
    # Relative to MEDIA_ROOT (the images/ dir); player uploads land in images/proposals/.
    logo = models.FileField(max_length=255, blank=True, upload_to="proposals/")
    banner = models.FileField(max_length=255, blank=True, upload_to="proposals/")
    primary_color = models.CharField(max_length=7, blank=True)  # "#rrggbb" or ""
    secondary_color = models.CharField(max_length=7, blank=True)
    subscriber_count = models.PositiveIntegerField(default=0)
    post_count = models.PositiveIntegerField(default=0)
    event_count = models.PositiveIntegerField(default=0)
    rarity = models.PositiveSmallIntegerField(
        choices=Rarity.choices, default=Rarity.COMMON, db_index=True
    )
    # Only approved cards can be pulled. Imported cards are approved; proposals start pending.
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.APPROVED, db_index=True)
    proposed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="proposals"
    )
    proposed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    @property
    def rarity_slug(self):
        return Rarity(self.rarity).name.lower()


class CardProposal(Card):
    """Admin-only view of Card for reviewing player proposals (its own tab in the admin)."""

    class Meta:
        proxy = True
        verbose_name = "proposed card"


class Pull(models.Model):
    """One card obtained by a user. A pack is 5 Pulls sharing the same opened_at."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pulls")
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="pulls")
    opened_at = models.DateTimeField(db_index=True)


class Friendship(models.Model):
    """A friend request from `from_user` to `to_user`; accepted once the recipient confirms it."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"

    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_sent")
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="friendships_received")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["from_user", "to_user"], name="unique_friendship_pair")]

    def __str__(self):
        return f"{self.from_user} -> {self.to_user} ({self.status})"
