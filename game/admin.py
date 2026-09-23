from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Card, Pull, User

admin.site.register(User, UserAdmin)
admin.site.register(Pull)


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["name", "rarity", "subscriber_count"]
    list_filter = ["rarity"]
    search_fields = ["name"]
