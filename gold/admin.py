from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from common.admin import ExportCsvMixin

from .models import GoldApplication, GoldChoice, GoldRule, GoldSignalSource
from .services import resend_barry_email


@admin.register(GoldApplication)
class GoldApplicationAdmin(ExportCsvMixin, SimpleHistoryAdmin):
    list_display = ("reference", "full_name", "email", "potential_level", "potential_score", "status", "email_sent_at", "created_at")
    list_filter = ("status", "potential_level", "property_link")
    search_fields = ("reference", "first_name", "last_name", "email", "company")
    readonly_fields = ("reference", "created_at", "updated_at", "email_sent_at", "email_error")
    actions = ["resend_email"]

    @admin.action(description="Resend the email to Barry")
    def resend_email(self, request, queryset):
        for application in queryset:
            resend_barry_email(application)


@admin.register(GoldRule)
class GoldRuleAdmin(SimpleHistoryAdmin):
    list_display = ("group", "match_value", "label", "points", "is_property", "active")
    list_filter = ("group", "active")


@admin.register(GoldChoice)
class GoldChoiceAdmin(SimpleHistoryAdmin):
    list_display = ("group", "value", "label", "order", "active")
    list_filter = ("group", "active")


@admin.register(GoldSignalSource)
class GoldSignalSourceAdmin(SimpleHistoryAdmin):
    list_display = ("signal", "question_key", "answer_value", "sets_value", "order", "active")
    list_filter = ("signal", "active")
