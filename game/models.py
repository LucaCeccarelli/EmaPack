from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # None = never opened a pack, so one is available right away.
    next_pack_at = models.DateTimeField(null=True, blank=True)


class Rarity(models.IntegerChoices):
    COMMON = 1, "Common"
    UNCOMMON = 2, "Uncommon"
    RARE = 3, "Rare"
    EPIC = 4, "Epic"
    LEGENDARY = 5, "Legendary"


class Card(models.Model):
    """One Komi page (a club or a member) turned into a collectible card."""

    komi_id = models.UUIDField(unique=True)
    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=500, blank=True)  # the page's short description line
    description = models.TextField(blank=True)  # text of the page's presentation blocks
    logo = models.FileField(blank=True)  # relative to MEDIA_ROOT (the images/ dir)
    banner = models.FileField(blank=True)
    primary_color = models.CharField(max_length=7, blank=True)  # "#rrggbb" or ""
    secondary_color = models.CharField(max_length=7, blank=True)
    subscriber_count = models.PositiveIntegerField(default=0)
    post_count = models.PositiveIntegerField(default=0)
    event_count = models.PositiveIntegerField(default=0)
    rarity = models.PositiveSmallIntegerField(
        choices=Rarity.choices, default=Rarity.COMMON, db_index=True
    )

    def __str__(self):
        return self.name

    @property
    def rarity_slug(self):
        return Rarity(self.rarity).name.lower()


class Pull(models.Model):
    """One card obtained by a user. A pack is 5 Pulls sharing the same opened_at."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pulls")
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="pulls")
    opened_at = models.DateTimeField(db_index=True)
