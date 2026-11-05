"""The add-your-number link (Office 2, docs/features/office-2-design.md section 9): each lead in the group email gets a personal link to a small public page where he gives the
mobile he has WhatsApp on.

The link is a signed token of his own address (django.core.signing, salted), valid for LINK_DAYS. Nothing is stored for it, nothing in it can be edited (a changed character fails the
signature), and the page trusts only the address inside it: it never looks anyone up by anything typed on the form. Expired and tampered links are answered with the same words, so a
guess learns nothing. The save is `outreach.services.add_number_from_link`."""
from django import forms
from django.conf import settings
from django.core import signing
from django.urls import reverse

from common.validators import normalise_mobile
from journey.copy import CONSENT_VERSION, GATE

SALT = "spa99.add-number.v1"
LINK_DAYS = 90  # the email says no deadline, and people read mail days later; three months, then the link ends (the page says so and points to WhatsApp)
MAX_AGE = LINK_DAYS * 24 * 3600


def make_token(email):
    return signing.dumps({"e": (email or "").strip().lower()}, salt=SALT, compress=True)


def read_token(token):
    """The address inside a good token, else None (tampered, expired, or not one of ours: the same answer for all)."""
    try:
        data = signing.loads(token or "", salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:  # includes SignatureExpired
        return None
    email = data.get("e") if isinstance(data, dict) else None
    return email.strip().lower() if isinstance(email, str) and email.strip() else None


def link_for(email):
    """His own link, on the public site (the Office host never serves this page)."""
    return f"{settings.SITE_URL}{reverse('add_number', args=[make_token(email)], urlconf='config.urls')}"


class AddNumberForm(forms.Form):
    first_name = forms.CharField(max_length=100, error_messages={"required": "Please add your name.", "max_length": "Please keep your name to 100 characters."})
    mobile_country = forms.CharField(required=False, max_length=2)
    mobile = forms.CharField(max_length=40, error_messages={"required": GATE["errors"]["mobile"]})
    consent = forms.BooleanField(error_messages={"required": "Please tick this so we can message you."})

    def clean_mobile(self):
        try:
            return normalise_mobile(self.cleaned_data["mobile"], self.data.get("mobile_country"))
        except forms.ValidationError:
            raise forms.ValidationError(GATE["errors"]["mobile"]) from None


CONSENT_TEXT = GATE["consent"]
TAKEN_TEXT = "That number is already with us. Please check it."
