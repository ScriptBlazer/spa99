"""The built-in wording of the footer under every email (System > Emails > Footer). Kept here so the models, the sending code and
the System screens share one copy. {site_name}, {address} and {contact_email} are filled in when an email is made."""
FOOTER_BRAND = "Beyond Luxury"
FOOTER_ADDRESS = "{site_name}, {address}"
FOOTER_CONTACT = "Questions? Reply to this email or write to {contact_email}."
FOOTER_LINE_MAX = 300
FOOTER_PLACEHOLDERS = {"site_name": "The site name (Spa 99)", "address": "The spa's address", "contact_email": "The contact address, shown as a link"}

# Per automatic email: which footer it uses, and who it comes from. "" in the database = that email's built-in default.
FOOTER_SHARED, FOOTER_NO_CONTACT, FOOTER_CUSTOM = "shared", "no_contact", "custom"
FOOTER_MODES = [(FOOTER_SHARED, "Shared footer"), (FOOTER_NO_CONTACT, "Shared footer without the contact line"), (FOOTER_CUSTOM, "Custom footer")]
SENDER_SITE, SENDER_PERSON = "site", "person"
SENDERS = [(SENDER_SITE, "Site sender"), (SENDER_PERSON, "Person sender")]
HEADING_MAX = 150
BUTTON_TEXT_MAX = 60
