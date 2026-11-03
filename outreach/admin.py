from django.contrib import admin

from .models import OutreachEntry, PersonMessage, StickyNote


@admin.register(StickyNote)
class StickyNoteAdmin(admin.ModelAdmin):
    list_display = ("email", "text", "author_label", "created_at", "deleted_at")
    search_fields = ("email", "text")
    list_filter = ("deleted_at",)
    readonly_fields = ("source_event",)


@admin.register(OutreachEntry)
class OutreachEntryAdmin(admin.ModelAdmin):
    list_display = ("pk", "user", "lead_email", "gold_application", "reason", "added_by_label", "added_at", "done_at")
    search_fields = ("lead_email", "reason")


@admin.register(PersonMessage)
class PersonMessageAdmin(admin.ModelAdmin):
    list_display = ("email", "author_label", "sent_at")
    search_fields = ("email", "text")
