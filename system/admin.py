import csv

from django.contrib import admin
from django.http import HttpResponse

from . import feed
from .models import SystemChange, SystemEvent


class ReadOnlyAudit(admin.ModelAdmin):
    """The audit log: read only, no delete (not even the bulk action), CSV export of the selected rows."""

    actions = ["export_csv"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Export selected rows as CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="system-audit.csv"'
        writer = csv.writer(response)
        writer.writerow(self.list_display)
        for row in queryset:
            writer.writerow([feed._safe(getattr(row, f)) for f in self.list_display])
        return response


@admin.register(SystemChange)
class SystemChangeAdmin(ReadOnlyAudit):
    list_display = ("created_at", "seq", "user_label", "ip_address", "section", "sentence", "old_value", "new_value")
    list_filter = ("section", "kind")
    search_fields = ("user_label", "object_repr", "field", "sentence", "ip_address")


@admin.register(SystemEvent)
class SystemEventAdmin(ReadOnlyAudit):
    list_display = ("created_at", "seq", "kind", "outcome", "user_label", "ip_address", "sentence")
    list_filter = ("kind", "outcome", "section")
    search_fields = ("user_label", "ip_address", "sentence", "path")
