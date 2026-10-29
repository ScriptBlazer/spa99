from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from common.admin import ExportCsvMixin

from . import approval, audit, invites
from .models import ApplicationEvent, ApproverDelivery, GoldApplication, GoldChoice, GoldInvite, GoldRule, GoldSignalSource
from .services import resend_approver_email


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


class ApplicationEventInline(admin.TabularInline):
    """The audit trail, read only: nobody adds, edits or deletes a row (docs/features/gold-actions.md)."""

    model = ApplicationEvent
    extra = 0
    fields = ("at", "action", "channel", "actor_label", "from_status", "to_status", "message", "meta")
    readonly_fields = fields
    can_delete = False
    ordering = ("-at",)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GoldApplication)
class GoldApplicationAdmin(ExportCsvMixin, SimpleHistoryAdmin):
    list_display = ("reference", "full_name", "email", "what_he_does", "potential_level", "potential_score", "status", "email_sent_at", "created_at")
    list_filter = ("status", "potential_level", "industry", "property_link", "business_willing")
    search_fields = ("reference", "first_name", "last_name", "email", "company")
    readonly_fields = ("reference", "created_at", "updated_at", "email_sent_at", "email_error", "approved_at", "approved_by",
                       "final_requested_at", "final_requested_by", "sent_back_at", "sent_back_by", "sent_back_note")
    inlines = [GoldInviteInline, ApplicationEventInline]
    actions = ["resend_email", "approve_and_invite", "resend_invite"]

    def save_model(self, request, obj, form, change):
        """A status changed in the admin form is recorded (who, from, to) in the same transaction."""
        with transaction.atomic():
            before = type(obj).objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change else None
            super().save_model(request, obj, form, change)
            if change and before != obj.status:  # not form.changed_data: a history Revert posts a different "before"
                audit.record(obj, ApplicationEvent.STATUS_CHANGED_ADMIN, actor=request.user, channel=audit.ADMIN, from_status=before, to_status=obj.status)

    @admin.display(description="Industry")
    def what_he_does(self, obj):
        return ", ".join(obj.industry_values)

    @admin.action(description="Approve and invite", permissions=["change"])
    def approve_and_invite(self, request, queryset):
        done = {invites.INVITED: 0, invites.ACTIVATED: 0, invites.SKIPPED: 0, approval.AWAITING: 0}
        for application in queryset:
            done[approval.approve(application, request.user, channel=audit.ADMIN)] += 1
            if application.status not in (GoldApplication.DECLINED, GoldApplication.APPROVED, GoldApplication.AWAITING_FINAL):
                self.message_user(request, f"{application.reference}: Gold could not be activated (is the Gold plan missing?). Nothing was changed or sent.", messages.ERROR)
        if done[invites.INVITED]:
            self.message_user(request, f"Approved and invited: {done[invites.INVITED]}.", messages.SUCCESS)
        if done[invites.ACTIVATED]:
            self.message_user(request, f"Approved, Gold added to their existing account: {done[invites.ACTIVATED]}.", messages.SUCCESS)
        if done[approval.AWAITING]:
            self.message_user(request, f"Sent for final approval: {done[approval.AWAITING]}.", messages.SUCCESS)
        if done[invites.SKIPPED]:
            self.message_user(request, f"Skipped (declined, already approved or awaiting final approval): {done[invites.SKIPPED]}.", messages.WARNING)

    @admin.action(description="Resend invite (the old link stops working)", permissions=["change"])
    def resend_invite(self, request, queryset):
        sent = sum(invites.resend_invite(a, request.user, channel=audit.ADMIN) == invites.INVITED for a in queryset)
        self.message_user(request, f"New invite sent: {sent}. Skipped: {len(queryset) - sent} (only approved applicants without an account get one).",
                          messages.SUCCESS if sent else messages.WARNING)

    @admin.action(description="Resend the approver email")
    def resend_email(self, request, queryset):
        for application in queryset:
            resend_approver_email(application)


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


@admin.register(ApplicationEvent)
class ApplicationEventAdmin(ExportCsvMixin, admin.ModelAdmin):
    """The Gold audit trail. Read only and exportable: no add, change or delete."""

    list_display = ("at", "application", "action", "channel", "actor_label", "from_status", "to_status")
    list_filter = ("action", "channel")
    search_fields = ("application__reference", "application__email", "actor_label", "message")
    readonly_fields = [f.name for f in ApplicationEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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


@admin.register(ApproverDelivery)
class ApproverDeliveryAdmin(ExportCsvMixin, admin.ModelAdmin):
    """Where a person's approval emails go. Set in System > Approval; the admin only shows it."""

    list_display = ("user", "use_account_email", "other_email")
    readonly_fields = ("user", "use_account_email", "other_email", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
