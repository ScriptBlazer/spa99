from django.contrib import admin

from common.admin import ExportCsvMixin

from .models import Contact, Message, PushSubscription, Template


@admin.register(Contact)
class ContactAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("phone", "name", "profile_name", "lead_email", "opted_out_at", "last_message_at")
    search_fields = ("phone", "name", "profile_name", "lead_email")
    readonly_fields = ("created_at",)


@admin.register(Message)
class MessageAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("id", "contact", "direction", "kind", "status", "created_at")
    list_filter = ("direction", "kind", "status")
    search_fields = ("contact__phone", "body", "twilio_sid")
    raw_id_fields = ("contact", "author", "template")


@admin.register(Template)
class TemplateAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("name", "language", "category", "approval_status", "synced_at")
    list_filter = ("approval_status",)
    search_fields = ("name", "content_sid")


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "user_agent", "created_at", "last_used_at")
    exclude = ("p256dh", "auth")  # keys are secrets: never shown
