from django.contrib import admin

from common.admin import ExportCsvMixin

from .models import EmailLog


@admin.register(EmailLog)
class EmailLogAdmin(ExportCsvMixin, admin.ModelAdmin):
    """Read-only send log."""

    list_display = ("created_at", "template", "to", "subject", "status")
    list_filter = ("status", "template")
    search_fields = ("to", "subject")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
