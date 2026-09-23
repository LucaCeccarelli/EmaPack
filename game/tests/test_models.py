from django.test import TestCase

from game.models import Card, Rarity, User


class ModelTests(TestCase):
    def test_new_user_has_a_pack_available(self):
        self.assertIsNone(User.objects.create_user("ash", password="pw").next_pack_at)

    def test_rarity_is_ordered_and_has_slug(self):
        self.assertLess(Rarity.COMMON, Rarity.LEGENDARY)
        card = Card.objects.create(
            komi_id="3ce8b812-6527-4668-8e86-5c3709de280a", name="BDE", rarity=Rarity.LEGENDARY
        )
        self.assertEqual(card.rarity_slug, "legendary")
        self.assertEqual(card.get_rarity_display(), "Legendary")
        self.assertEqual(str(card), "BDE")
