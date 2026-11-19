from django.contrib import admin

from common.admin import ExportCsvMixin

from .models import MembershipReview, MembershipReviewEvent


@admin.register(MembershipReview)
class MembershipReviewAdmin(ExportCsvMixin, admin.ModelAdmin):
    """Barry's review of each registration. Read-mostly: decisions are made in the Office (Approvals), where they are audited."""

    list_display = ("registration", "status", "by_label", "at")
    list_filter = ("status",)
    readonly_fields = ("registration", "by", "by_label", "at")


@admin.register(MembershipReviewEvent)
class MembershipReviewEventAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("registration", "from_status", "to_status", "by_label", "at")
    list_filter = ("to_status",)
    readonly_fields = ("registration", "from_status", "to_status", "by", "by_label", "at")

    def has_add_permission(self, request):
        return False
