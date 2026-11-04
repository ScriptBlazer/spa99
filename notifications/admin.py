from django.contrib import admin

from simple_history.admin import SimpleHistoryAdmin

from common import richtext
from common.admin import ExportCsvMixin

from .models import EmailBounce, EmailLog, EmailSuppression, NotificationTemplate, StaffSender


@admin.register(EmailLog)
class EmailLogAdmin(ExportCsvMixin, admin.ModelAdmin):
    """Read-only send log."""

    list_display = ("created_at", "template", "to", "subject", "status")
    list_filter = ("status", "template")
    search_fields = ("to", "subject", "subject_email")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(SimpleHistoryAdmin):
    list_display = ("key", "subject", "note")


@admin.register(EmailSuppression)
class EmailSuppressionAdmin(ExportCsvMixin, admin.ModelAdmin):
    """Read-only. Removing an address is done in System (it is audit logged)."""

    list_display = ("email", "reason", "last_seen", "count")
    list_filter = ("reason",)
    search_fields = ("email",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailBounce)
class EmailBounceAdmin(ExportCsvMixin, admin.ModelAdmin):
    """Read-only log of Postmark bounces and complaints (also shown in System > Emails > Bounces)."""

    list_display = ("received_at", "email", "kind", "postmark_type")
    list_filter = ("kind",)
    search_fields = ("email",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(StaffSender)
class StaffSenderAdmin(admin.ModelAdmin):
    """A team member's sending address and signature (also edited in System > Team > Email). The signature is cleaned on save here too."""
    list_display = ("user", "sending_address", "updated_at")
    search_fields = ("user__email", "sending_address")
    raw_id_fields = ("user",)

    def save_model(self, request, obj, form, change):
        obj.signature_html = richtext.clean_signature(obj.signature_html)
        super().save_model(request, obj, form, change)
