from django.contrib import admin

from common.admin import ExportCsvMixin

from . import services
from .models import Attachment, Message, Thread


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("direction", "subject", "status", "created_at")
    readonly_fields = fields
    show_change_link = True
    can_delete = False


@admin.register(Thread)
class ThreadAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("subject", "email", "name", "last_message_at")
    search_fields = ("subject", "email", "name")
    readonly_fields = ("token", "created_at")
    raw_id_fields = ("user", "application", "created_by")
    inlines = [MessageInline]

    def delete_model(self, request, obj):  # UK GDPR: files in storage and queue records go too, not just the rows
        services.erase_threads([obj])

    def delete_queryset(self, request, queryset):
        services.erase_threads(list(queryset))


@admin.register(Message)
class MessageAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("id", "thread", "direction", "subject", "status", "spam", "created_at")
    list_filter = ("direction", "status", "spam")
    search_fields = ("thread__email", "subject", "body_text", "provider_id")
    raw_id_fields = ("thread", "author")
    exclude = ("body_html",)  # the cleaned HTML is shown in the Office only, in a sandbox

    def delete_model(self, request, obj):  # UK GDPR: the files in storage go too, and the thread's last line is repaired
        services.erase_message(obj)

    def delete_queryset(self, request, queryset):
        for message in list(queryset.select_related("thread")):
            services.erase_message(message)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("filename", "message", "content_type", "size", "inline_ok")
    raw_id_fields = ("message",)

    def delete_model(self, request, obj):  # the file in storage goes with the row
        services.erase_attachments([obj])

    def delete_queryset(self, request, queryset):
        services.erase_attachments(list(queryset))
