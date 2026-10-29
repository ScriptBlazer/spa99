from django import forms
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from common.admin import ExportCsvMixin

from content import images

from .models import Closure, Facility, OpeningRule, PaymentMark, PaymentNotice, PaymentStaffAlert, PaymentWindow, Plan, Sale, SiteSettings, Subscription


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
    list_display = ("name", "slug", "display", "order", "visible")
    list_editable = ("display", "order", "visible")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Sale)
class SaleAdmin(ExportCsvMixin, SimpleHistoryAdmin):
    """See and export only: sales are made and ended in System > Sales (overlap and live locks, audit log, undo)."""
    list_display = ("name", "percent_off", "starts_at", "ends_at", "ended_early_at", "months_at_price")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(ExportCsvMixin, admin.ModelAdmin):
    """Payment window records: visible and exportable for Moishe, changed only through System > Payments and the Office."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentWindow)
class PaymentWindowAdmin(ReadOnlyAdmin):
    list_display = ("status", "scheduled_for", "opened_at", "closes_at", "closed_at", "opened_by")


@admin.register(PaymentNotice)
class PaymentNoticeAdmin(ReadOnlyAdmin):
    list_display = ("window", "registration", "kind", "status", "sent_at")
    list_filter = ("kind", "status")


@admin.register(Subscription)
class SubscriptionAdmin(ReadOnlyAdmin):
    list_display = ("registration", "plan", "source", "status", "start_date", "agreed_price_ex_vat")
    list_filter = ("source", "status")


@admin.register(PaymentMark)
class PaymentMarkAdmin(ReadOnlyAdmin):
    list_display = ("registration", "source", "idempotency_key", "created_at")


@admin.register(PaymentStaffAlert)
class PaymentStaffAlertAdmin(ReadOnlyAdmin):
    list_display = ("window", "day", "at_risk", "emailed")
