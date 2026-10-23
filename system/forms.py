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
    class Meta:
        model = SiteSettings
        fields = ["opening_date", "opening_text", "register_interest_open", "subscribe_open", "booking_open",
                  "join_wording", "vat_rate"]
        widgets = {"opening_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
