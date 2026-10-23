from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from simple_history.admin import SimpleHistoryAdmin

from common.admin import ExportCsvMixin

from . import services
from .forms import UserChangeForm, UserCreationForm
from .models import InterestRegistration, User


@admin.register(User)
class UserAdmin(ExportCsvMixin, SimpleHistoryAdmin, BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    ordering = ("email",)
    list_display = ("email", "public_id", "first_name", "last_name", "is_staff", "is_active", "created_at")
    list_filter = ("is_staff", "is_active", "marketing_consent")
    search_fields = ("email", "first_name", "last_name", "mobile", "public_id")
    # Verification and marketing choice feed the stored Office figures: changed by the services only, not by hand here.
    readonly_fields = ("public_id", "created_at", "updated_at", "last_login", "email_verified_at", "marketing_consent")

    def delete_model(self, request, obj):
        services.delete_user_data(obj)  # full erasure, and the stored figures move with it

    def delete_queryset(self, request, queryset):
        for user in queryset:
            services.delete_user_data(user)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Person", {"fields": ("public_id", "first_name", "last_name", "mobile", "date_of_birth")}),
        ("Consent and verification", {
            "fields": ("email_verified_at", "marketing_consent", "marketing_consent_at",
                       "privacy_accepted_version", "privacy_accepted_at", "men_only_accepted_at"),
        }),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "usable_password", "password1", "password2")}),)


@admin.register(InterestRegistration)
class InterestRegistrationAdmin(ExportCsvMixin, SimpleHistoryAdmin):
    list_display = ("user", "plan", "source", "created_at")
    list_filter = ("plan", "source")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    date_hierarchy = "created_at"
    readonly_fields = ("user", "source", "journey_session")  # the plan stays editable: its change is counted by a signal

    def has_add_permission(self, request):
        return False  # created by sign-up, which counts it

    def has_delete_permission(self, request, obj=None):
        return False  # delete the person instead (UserAdmin): that erases and un-counts them
