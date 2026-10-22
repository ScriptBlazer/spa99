from django import forms
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from common.admin import ExportCsvMixin

from content import images

from .models import Closure, Facility, OpeningRule, Plan, SiteSettings


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = "__all__"

    def clean_render(self):
        name = self.cleaned_data.get("render", "")
        if name and not images.has_image(name):
            raise forms.ValidationError("No built render with this name.")
        return name


@admin.register(Plan)
class PlanAdmin(ExportCsvMixin, SimpleHistoryAdmin):
    form = PlanForm
    list_display = ("name", "slug", "kind", "price_ex_vat", "visits_per_month", "hours", "highlight", "visible", "order")
    list_editable = ("order", "visible")


@admin.register(SiteSettings)
class SiteSettingsAdmin(SimpleHistoryAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OpeningRule)
class OpeningRuleAdmin(SimpleHistoryAdmin):
    list_display = ("label", "key", "kind", "start_time", "end_time", "offset_minutes", "active", "order")


@admin.register(Closure)
class ClosureAdmin(SimpleHistoryAdmin):
    list_display = ("name", "starts_at", "ends_at", "active")


@admin.register(Facility)
class FacilityAdmin(SimpleHistoryAdmin):
    list_display = ("name", "slug", "order", "visible")
    list_editable = ("order", "visible")
    prepopulated_fields = {"slug": ("name",)}
