from django.contrib import admin

from .models import SystemChange


@admin.register(SystemChange)
class SystemChangeAdmin(admin.ModelAdmin):
    """The change log: read only (undo is done in System, which adds a new entry)."""

    list_display = ("created_at", "user_label", "section", "model_label", "object_repr", "field", "old_value", "new_value")
    list_filter = ("section", "kind")
    search_fields = ("user_label", "object_repr", "field")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
