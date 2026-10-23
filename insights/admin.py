from django.contrib import admin

from .models import DailyMetric, MetricCounter, MetricText, OfficeGoal, PeriodMetric


@admin.register(OfficeGoal)
class OfficeGoalAdmin(admin.ModelAdmin):
    """Goals for the dashboard rings. No row = "No goal set"."""

    list_display = ("key", "range", "target")
    list_filter = ("key",)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Stored figures are written by the app and the roll-up, never by hand (use rebuild_metrics to repair)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MetricCounter)
class MetricCounterAdmin(ReadOnlyAdmin):
    list_display = ("key", "dimension", "value", "updated_at")
    list_filter = ("key",)


@admin.register(DailyMetric)
class DailyMetricAdmin(ReadOnlyAdmin):
    list_display = ("date", "key", "dimension", "value")
    list_filter = ("key",)
    date_hierarchy = "date"


@admin.register(PeriodMetric)
class PeriodMetricAdmin(ReadOnlyAdmin):
    list_display = ("period", "start", "key", "dimension", "value")
    list_filter = ("period", "key")


@admin.register(MetricText)
class MetricTextAdmin(ReadOnlyAdmin):
    list_display = ("key", "scope", "text", "updated_at")
