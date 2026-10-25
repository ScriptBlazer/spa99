from django import forms

from plans.models import SiteSettings


class EmailsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = ["gold_approver_emails", "gold_approver_cc", "contact_email"]

    def clean(self):
        data = super().clean()
        data["contact_email"] = self._single(data.get("contact_email", ""))
        return data

    @staticmethod
    def _single(value):
        from common.validators import split_emails

        if len(split_emails(value)) > 1:
            raise forms.ValidationError({"contact_email": "Enter one address."})
        return value


class SettingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["register_interest_open"].label = "Registration open"
        for name, low, high in (("lock_idle_minutes", 1, 240), ("max_sign_in_hours", 1, 72)):
            self.fields[name].widget.attrs.update({"min": low, "max": high})
            self.fields[name].min_value, self.fields[name].max_value = low, high

    def clean_vat_rate(self):
        rate = self.cleaned_data["vat_rate"]
        if rate < 0 or rate > 100:
            raise forms.ValidationError("Enter a rate between 0 and 100.")
        return rate

    class Meta:
        model = SiteSettings
        fields = ["opening_date", "opening_text", "register_interest_open", "subscribe_open", "booking_open",
                  "join_wording", "vat_rate", "lock_idle_minutes", "max_sign_in_hours"]
        widgets = {"opening_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
