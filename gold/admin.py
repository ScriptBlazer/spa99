from django.contrib import admin, messages
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from common.admin import ExportCsvMixin

from . import invites
from .models import GoldApplication, GoldChoice, GoldInvite, GoldRule, GoldSignalSource
from .services import resend_barry_email


class GoldInviteInline(admin.TabularInline):
    """Invite status, read only: sent, expires, used."""

    model = GoldInvite
    extra = 0
    fields = ("created_at", "sent_at", "expires_at", "used_at", "revoked_at", "status")
    readonly_fields = fields
    can_delete = False

    @admin.display(description="Status")
    def status(self, obj):
        if obj.used_at:
            return "Used"
        if obj.revoked_at:
            return "Replaced by a newer link"
        return "Expired" if obj.expires_at <= timezone.now() else "Waiting"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(GoldApplication)
class GoldApplicationAdmin(ExportCsvMixin, SimpleHistoryAdmin):
    list_display = ("reference", "full_name", "email", "potential_level", "potential_score", "status", "email_sent_at", "created_at")
    list_filter = ("status", "potential_level", "industry", "property_link")
    search_fields = ("reference", "first_name", "last_name", "email", "company")
    readonly_fields = ("reference", "created_at", "updated_at", "email_sent_at", "email_error", "approved_at", "approved_by")
    inlines = [GoldInviteInline]
    actions = ["resend_email", "approve_and_invite", "resend_invite"]

    @admin.action(description="Approve and invite", permissions=["change"])
    def approve_and_invite(self, request, queryset):
        done = {invites.INVITED: 0, invites.ACTIVATED: 0, invites.SKIPPED: 0}
        for application in queryset:
            done[invites.approve_and_invite(application, request.user)] += 1
        if done[invites.INVITED]:
            self.message_user(request, f"Approved and invited: {done[invites.INVITED]}.", messages.SUCCESS)
        if done[invites.ACTIVATED]:
            self.message_user(request, f"Approved, Gold added to their existing account: {done[invites.ACTIVATED]}.", messages.SUCCESS)
        if done[invites.SKIPPED]:
            self.message_user(request, f"Skipped (declined or already approved): {done[invites.SKIPPED]}.", messages.WARNING)

    @admin.action(description="Resend invite (the old link stops working)", permissions=["change"])
    def resend_invite(self, request, queryset):
        sent = sum(invites.resend_invite(a) == invites.INVITED for a in queryset)
        self.message_user(request, f"New invite sent: {sent}. Skipped: {len(queryset) - sent} (only approved applicants without an account get one).",
                          messages.SUCCESS if sent else messages.WARNING)

    @admin.action(description="Resend the email to Barry")
    def resend_email(self, request, queryset):
        for application in queryset:
            resend_barry_email(application)


@admin.register(GoldRule)
class GoldRuleAdmin(SimpleHistoryAdmin):
    list_display = ("group", "match_value", "label", "points", "is_property", "active")
    list_filter = ("group", "active")


@admin.register(GoldChoice)
class GoldChoiceAdmin(SimpleHistoryAdmin):
    list_display = ("group", "value", "label", "order", "active")
    list_filter = ("group", "active")


@admin.register(GoldSignalSource)
class GoldSignalSourceAdmin(SimpleHistoryAdmin):
    list_display = ("signal", "question_key", "answer_value", "sets_value", "order", "active")
    list_filter = ("signal", "active")


@admin.register(GoldInvite)
class GoldInviteAdmin(admin.ModelAdmin):
    """Read only: invites are made by 'Approve and invite' and 'Resend invite' on the application."""

    list_display = ("application", "created_at", "sent_at", "expires_at", "used_at", "revoked_at")
    list_filter = ("used_at", "revoked_at")
    search_fields = ("application__reference", "application__email")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
