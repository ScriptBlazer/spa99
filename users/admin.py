from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from simple_history.admin import SimpleHistoryAdmin

from common.admin import ExportCsvMixin

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
    readonly_fields = ("public_id", "created_at", "updated_at", "last_login")
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
