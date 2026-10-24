"""Read the emails the site wrote to the throwaway email folder (Django's file-based backend), to follow links like a person."""
import email
import email.policy
import os
import re
import time
from pathlib import Path

SEPARATOR = re.compile(rb"\r?\n-{79}\r?\n")
URL = re.compile(r"https?://[^\s<>\"']+")


def folder():
    return Path(os.environ["E2E_WORKSPACE"]) / "mail"


def messages():
    """Every email so far, oldest first, as parsed messages."""
    found = []
    for path in sorted(folder().glob("*.log")):
        for chunk in SEPARATOR.split(path.read_bytes()):
            if chunk.strip():
                found.append(email.message_from_bytes(chunk, policy=email.policy.default))
    return found


def recipients(message):
    return " ".join(str(message.get(header, "")) for header in ("To", "Cc")).lower()


def find(to, subject_has):
    """The newest email to (or cc) `to` whose subject contains `subject_has`, or None."""
    for message in reversed(messages()):
        if to.lower() in recipients(message) and subject_has.lower() in str(message["Subject"]).lower():
            return message
    return None


def wait_for(to, subject_has, timeout=20):
    """Wait for an email (jobs run inline, so it is normally already there). Raises with what WAS sent, to make a failure readable."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        message = find(to, subject_has)
        if message is not None:
            return message
        time.sleep(0.4)
    seen = [f"to {recipients(m).strip()}: {m['Subject']}" for m in messages()]
    raise AssertionError(f"No email to {to} with a subject containing '{subject_has}'. Emails sent so far: {seen or 'none'}")


def body(message):
    part = message.get_body(preferencelist=("plain", "html"))
    return part.get_content() if part is not None else ""


def link(message, contains):
    """The first link in the email whose address contains `contains` (for example '/verify/')."""
    for url in URL.findall(body(message)):
        url = url.rstrip(".,);")
        if contains in url:
            return url
    raise AssertionError(f"No link containing '{contains}' in the email '{message['Subject']}'.")


def count_to(to):
    return sum(1 for message in messages() if to.lower() in recipients(message))


def html_body(message):
    part = message.get_body(preferencelist=("html",))
    return part.get_content() if part is not None else ""


def text_body(message):
    part = message.get_body(preferencelist=("plain",))
    return part.get_content() if part is not None else ""


def subjects_to(to):
    """The subjects of every email sent to (or cc'd to) `to`, oldest first."""
    return [str(m["Subject"]) for m in messages() if to.lower() in recipients(m)]


def count_subject(to, subject_has):
    return sum(1 for m in messages() if to.lower() in recipients(m) and subject_has.lower() in str(m["Subject"]).lower())
