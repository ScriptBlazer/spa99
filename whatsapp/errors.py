"""Twilio's error codes, in plain words for the chat (design brief section 3). The code itself never shows to staff.
The codes below are from Twilio's WhatsApp error reference; any code we do not know reads "Not sent. Try again.". `reason(message)`
returns (text, can_retry)."""

WINDOW_CLOSED = {"63016"}  # free-form message outside the 24-hour window
NOT_ON_WHATSAPP = {"63024", "63003", "63007", "21211", "21614", "21612"}  # no such WhatsApp user / not a mobile / bad To
NOT_DELIVERED = {"63049", "63013", "63032", "63051"}  # WhatsApp chose not to deliver (quality, policy, marketing limits)
SENDING_STOPPED = {"20003", "20005", "20008", "63038", "63015"}  # authentication, account, daily limit, sandbox: nothing will go until it is fixed
TOO_BIG = {"63021", "63005"}  # media too big or not supported

TRY_AGAIN = "Not sent. Try again."
MAYBE_NOT_SENT = "This may not have been sent. Check the chat on his phone if you can, then try again."


def reason(code="", http_status=None):
    """Plain reason and whether 'Try again' makes sense, from a Twilio error code (or an HTTP status when there is no code)."""
    code = str(code or "")
    if code == "opted_out":
        return "Not sent. He replied STOP.", False
    if code in WINDOW_CLOSED:
        return "Not sent. The window has closed.", False
    if code in NOT_ON_WHATSAPP:
        return "Not delivered. He may not be on WhatsApp.", False
    if code in NOT_DELIVERED:
        return "Not delivered. WhatsApp chose not to deliver this one.", False
    if code in SENDING_STOPPED or http_status in (401, 402, 403):
        return "Not sent. Sending has stopped, check the Twilio balance.", True
    if code in TOO_BIG:
        return "Not sent. The file was refused (too big or not a supported type).", False
    return TRY_AGAIN, True
