from django.contrib import admin

from .models import Call


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    """Read-only: calls are made by Twilio's webhooks and the import, never typed."""

    list_display = ("received_at", "from_number", "kind", "duration_seconds", "source", "audio_saved_at", "emailed_at", "attempts", "heard_at")
    list_filter = ("kind", "source")
    search_fields = ("from_number", "call_sid", "recording_sid")
    date_hierarchy = "received_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
