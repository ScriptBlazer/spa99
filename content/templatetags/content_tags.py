from django import template

from content import images, services

register = template.Library()


@register.simple_tag
def page_content(page_key):
    """{% page_content "home" as home %} then {{ home.hero.heading }}."""
    return services.page_content(page_key)


@register.inclusion_tag("users/_discount_line.html", takes_context=True)
def discount_line(context):
    """{% discount_line %}: 'Looking for a better rate? Message us on WhatsApp.' with the Site settings link. Empty link:
    a marked 'link to come' on dev, nothing on live (same rule as the legal fill-later rows)."""
    from django.conf import settings

    from plans.models import SiteSettings

    site = context.get("site_settings") or SiteSettings.load()
    return {"url": site.discount_contact_url, "show_placeholder": settings.DEBUG}


@register.inclusion_tag("content/_gold_fee_note.html")
def gold_fee_note(css_class="fee-note"):
    """{% gold_fee_note %}: '*An annual admin fee of £199 + VAT applies.' from the Gold plan's annual fee; nothing while empty."""
    from plans.services import gold_fee_note as note

    return {"note": note(), "css_class": css_class}


@register.simple_tag
def photo(name, alt="", sizes="100vw", eager=False, override=None, css_class=""):
    """{% photo "dry-sauna" alt="..." sizes="(min-width: 64em) 60vw, 100vw" override=section.image %}"""
    return images.picture(name, alt=alt, sizes=sizes, eager=eager, override=override, css_class=css_class)


@register.filter
def lines(text):
    """Split a text block into its non-empty lines."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


@register.simple_tag
def photo_srcset(name):
    """The WebP srcset of an optimised render, for <link rel="preload" imagesrcset>."""
    return images.srcset(name) if images.has_image(name) else ""


@register.filter
def parts(sections, prefix="part_"):
    """The sections of a page whose key starts with `prefix`, in order (the numbered parts of a legal page)."""
    return [section for key, section in sections.items() if key.startswith(prefix)]


@register.simple_tag(takes_context=True)
def legal_text(context, text, doc=None):
    """{% legal_text part.body doc %}: a legal body as safe HTML (format in content/legal.py). The contact email and the
    privacy version come from Site settings; {ico} / {hosting} from the privacy page rows, marked on dev while empty."""
    from django.conf import settings

    from content import legal_render
    from plans.models import SiteSettings

    site = context.get("site_settings") or SiteSettings.load()
    values = {}
    if any("{" + key + "}" in (text or "") for key in legal_render.PLACEHOLDERS):
        rows = doc if doc is not None and context.get("page_key") == "privacy" else services.page_content("privacy")
        values = {key: rows[key].body for key in legal_render.PLACEHOLDERS}
    return legal_render.render(text, contact=site.contact_address, version=site.privacy_version, values=values,
                               show_placeholders=settings.DEBUG)


@register.inclusion_tag("users/_payment_note.html")
def payment_note(whatsapp=True, css_class="no-payment", status=""):
    """{% payment_note %}: 'No payment is taken now. When we open, you'll have 2 weeks to set up your membership.' (the length is the
    payment window in System > Defaults) and, for a special discount, a WhatsApp link from Site settings (the line is left out when no link is set)."""
    from django.conf import settings

    from plans import payments
    from plans.models import SiteSettings

    return {"opened": payments.opened_ever(), "live": settings.ONLINE_PAYMENTS_LIVE, "paid": status == "paid", "window": payments.site_window_phrase(),
            "url": payments.whatsapp_url() if whatsapp or payments.opened_ever() else "", "email": SiteSettings.load().contact_address, "css_class": css_class}
