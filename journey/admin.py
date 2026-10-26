from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from common.admin import ExportCsvMixin

from .models import Answer, JourneySession, Option, Question, SuggestionRule


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0
    fields = ("label", "value", "order", "active", "plan_points", "gold_points", "weight", "reason")


@admin.register(Question)
class QuestionAdmin(SimpleHistoryAdmin):
    list_display = ("key", "text", "type", "screen", "order", "min_choices", "active")
    list_filter = ("screen", "active", "type")
    inlines = [OptionInline]


@admin.register(Option)
class OptionAdmin(SimpleHistoryAdmin):
    list_display = ("question", "label", "value", "order", "active", "plan_points", "gold_points")
    list_filter = ("question", "active")


@admin.register(SuggestionRule)
class SuggestionRuleAdmin(SimpleHistoryAdmin):
    list_display = ("name", "kind", "plan_slugs", "points", "active", "order")


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    can_delete = False
    readonly_fields = ("question", "options", "text_value", "skipped", "answered_at")


@admin.register(JourneySession)
class JourneySessionAdmin(ExportCsvMixin, SimpleHistoryAdmin):
    list_display = ("created_at", "device_type", "current_step", "completed", "suggested_plan", "gold_potential", "lead_email", "user", "is_bot")
    list_filter = ("completed", "device_type", "gold_potential", "is_bot")
    search_fields = ("user__email", "lead_email", "utm_source", "referrer")
    readonly_fields = ("created_at", "updated_at")
    export_exclude = ("key",)  # the cookie value is a secret: hidden from the form and from CSV
    exclude = ("key",)
    inlines = [AnswerInline]

    # Sessions feed the stored Office figures (starts, reach, completions, answers): read only here.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Answer)
class AnswerAdmin(ExportCsvMixin, SimpleHistoryAdmin):
    list_display = ("session", "question", "skipped", "answered_at")
    list_filter = ("question", "skipped")
