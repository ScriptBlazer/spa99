from django import template
from django.urls import NoReverseMatch, reverse
from django.utils.html import json_script

from common.validators import client_config

register = template.Library()


@register.simple_tag
def validation_config():
    """{% validation_config %} once in any page with a live-validated form. validate.js reads it, so the messages
    and limits are the Python ones (common/validators.py), never copies."""
    try:
        urls = {"mobile": reverse("check_mobile")}
    except NoReverseMatch:  # Spa 99 Control has no public sign-up, so no mobile check
        urls = {}
    return json_script(client_config(urls), "validation-config")
