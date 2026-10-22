import csv

from django.contrib import admin
from django.http import HttpResponse

from .models import LoginEvent

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value):
    """Stop spreadsheet formula injection when the CSV is opened in Excel."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


class ExportCsvMixin:
    """Admin action: export selected rows as CSV. Set `export_exclude` to hide fields (password is always hidden)."""

    export_exclude = ()

    @admin.action(description="Export selected rows as CSV")
    def export_selected_csv(self, request, queryset):
        excluded = {"password", *self.export_exclude}
        fields = [f for f in self.model._meta.concrete_fields if f.name not in excluded]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{self.model._meta.model_name}.csv"'
        writer = csv.writer(response)
        writer.writerow([f.name for f in fields])
        for row in queryset.iterator():
            writer.writerow([_safe_cell(f.value_from_object(row)) for f in fields])
        return response

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions["export_selected_csv"] = self.get_action("export_selected_csv")
        return actions


@admin.register(LoginEvent)
class LoginEventAdmin(ExportCsvMixin, admin.ModelAdmin):
    """Read-only: audit records are never edited or deleted."""

    list_display = ("created_at", "event", "attempted_email", "user", "ip_address")
    list_filter = ("event",)
    search_fields = ("attempted_email", "ip_address")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
