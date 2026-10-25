from django.contrib import admin

from common.admin import ExportCsvMixin

from .models import EmailOptOut, Invite, Mailing, MailingRecipient


class ReadOnlyMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Mailing)
class MailingAdmin(ReadOnlyMixin, ExportCsvMixin, admin.ModelAdmin):
    """Read-only: mailings are made and sent in System > Emails (every send is audit logged there)."""

    list_display = ("name", "kind", "group", "status", "total_count", "sent_count", "created_at")
    list_filter = ("status", "kind", "group")


@admin.register(MailingRecipient)
class MailingRecipientAdmin(ReadOnlyMixin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("email", "mailing", "status", "reason", "sent_at")
    list_filter = ("status",)
    search_fields = ("email",)


@admin.register(Invite)
class InviteAdmin(ReadOnlyMixin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("email", "name", "status", "sent_at", "opened_at", "registered_at")
    list_filter = ("status",)
    search_fields = ("email", "name")


@admin.register(EmailOptOut)
class EmailOptOutAdmin(ReadOnlyMixin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("email", "source", "created_at")
    search_fields = ("email",)
