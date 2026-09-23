from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .models import Card, CardProposal, Pull, Status, User

admin.site.register(User, UserAdmin)
admin.site.register(Pull)


def thumb(image):
    return format_html('<img src="{}" style="height:48px;border-radius:6px">', image.url) if image else "—"


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["name", "rarity", "subscriber_count"]
    list_filter = ["rarity"]
    search_fields = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=Status.APPROVED)


@admin.register(CardProposal)
class CardProposalAdmin(admin.ModelAdmin):
    """Review player proposals: set the rarity, then approve (it joins the packs) or reject."""

    list_display = ["name", "logo_preview", "proposed_by", "rarity", "status"]
    list_editable = ["rarity"]
    list_filter = ["status"]
    search_fields = ["name", "proposed_by__username"]
    ordering = ["-proposed_at"]
    actions = ["approve", "reject"]
    fields = ["status", "rarity", "name", "tagline", "description", "logo_preview", "logo",
              "banner_preview", "banner", "primary_color", "secondary_color", "proposed_by", "proposed_at"]
    readonly_fields = ["logo_preview", "banner_preview", "proposed_by", "proposed_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(proposed_by__isnull=False)

    def has_add_permission(self, request):
        return False  # proposals come from players, via the "Propose" page

    @admin.display(description="Logo")
    def logo_preview(self, obj):
        return thumb(obj.logo)

    @admin.display(description="Banner")
    def banner_preview(self, obj):
        return thumb(obj.banner)

    @admin.action(description="Approve selected cards (they can be pulled from packs)")
    def approve(self, request, queryset):
        n = queryset.update(status=Status.APPROVED)
        self.message_user(request, f"{n} card(s) approved and added to the packs.", messages.SUCCESS)

    @admin.action(description="Reject selected cards")
    def reject(self, request, queryset):
        n = queryset.update(status=Status.REJECTED)
        self.message_user(request, f"{n} card(s) rejected.", messages.WARNING)
