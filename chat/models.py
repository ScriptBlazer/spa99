"""The "Ask us" chat (docs/features/ai-chat.md): saved conversations (deleted after 90 days) and the FAQ Moishe edits in System.

Conversation and Message have no django-simple-history on purpose (one line): they are append-only logs that are deleted after
90 days, and a history table would copy the chat text for ever. The FAQ is ordinary editable data, so it has history (the change log)."""
import logging

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import DatabaseError, models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from common.models import BaseModel


class FaqItem(BaseModel):
    """One question and answer the assistant may use, and the panel may suggest. Edited in System > FAQ."""

    question = models.CharField(max_length=200)
    answer = models.TextField(max_length=1500, help_text="Plain words, as the site would say it. The assistant answers from this and never goes beyond it.")
    order = models.PositiveSmallIntegerField(default=0)
    visible = models.BooleanField(default=True, help_text="Hidden entries are not given to the assistant.")
    suggested = models.BooleanField(default=False, help_text="Shown as a tap-to-ask question when the chat opens (the first four, in order).")

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "question"]
        verbose_name = "FAQ entry"
        verbose_name_plural = "FAQ"

    def __str__(self):
        return self.question


class KnowledgeNote(BaseModel):
    """A short fact the assistant may use, by topic (System > Assistant > Knowledge notes). Never a price: prices come only from the
    plans, under the price rule, so a "£" is refused."""

    TOPICS = [("facilities", "Facilities"), ("lockers", "Lockers and changing"), ("booking", "Booking"), ("memberships", "Memberships"),
              ("gold", "Gold Card"), ("visiting", "Visiting and arrival"), ("policies", "Policies"), ("other", "Other")]

    topic = models.CharField(max_length=12, choices=TOPICS, default="other")
    title = models.CharField(max_length=120)
    text = models.TextField(max_length=1500, help_text="Plain words, as the site would say it. No prices: they come from the plans.")
    order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True, help_text="Inactive notes are not given to the assistant.")

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title


def _number(label, default, low, high, help_text=""):
    return models.PositiveSmallIntegerField(label, default=default, validators=[MinValueValidator(low), MaxValueValidator(high)], help_text=help_text)


class AssistantSettings(BaseModel):
    """The assistant's voice and limits (singleton, `load()`), edited in System > Assistant. Everything here feeds the system prompt
    or the guards; the hard rules (scope, no price before an email, no code, off-topic closing) stay in code and cannot be edited away.
    The monthly cap stays on system.SiteDefaults (chat_monthly_cap_gbp) so no data moves."""

    singleton_key = models.CharField(max_length=10, default="site", unique=True, editable=False)
    enabled = models.BooleanField("Assistant on", default=True, help_text="Off hides the Ask us button and refuses every chat request at once.")

    name = models.CharField("Assistant name", max_length=40, default="Spa 99 Assistant")
    welcome_heading = models.CharField(max_length=80, default="Ask us anything.")
    welcome_line = models.CharField(max_length=160, default="The spa, memberships, hours or the Gold Card.", blank=True)
    tone_notes = models.TextField("Tone notes", max_length=600, blank=True, help_text="How it should sound, in a few words. Added to the built-in tone (calm, brief, British English).")
    always = models.TextField("Always", max_length=800, blank=True, help_text="One line each: things it should always do.")
    never = models.TextField("Never", max_length=800, blank=True, help_text="One line each: things it should never do (added to the built-in never list).")

    daily_cap_percent = _number("Daily soft cap (% of the monthly cap)", 5, 1, 100, "At this share of the monthly cap, only the hand-off shows until tomorrow.")
    rate_per_10_minutes = _number("Messages per 10 minutes", 10, 1, 60, "Per browser and per IP address.")
    rate_per_day = _number("Messages per day", 40, 1, 500, "Per browser and per IP address.")
    max_messages = _number("Messages in one conversation", 12, 2, 40)
    max_chars = _number("Characters in one message", 500, 50, 1000, "The panel shows this limit.")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "assistant settings"
        verbose_name_plural = "assistant settings"

    def __str__(self):
        return "Assistant settings"

    @classmethod
    def load(cls):
        """The one row (made on first read). If the database cannot be read it returns an unsaved copy with the defaults."""
        try:
            obj, _ = cls.objects.get_or_create(singleton_key="site")
            return obj
        except DatabaseError:
            logging.getLogger("spa99.chat").warning("Assistant settings not readable; using the defaults", exc_info=True)
            return cls()

    @staticmethod
    def lines(text, limit=12):
        return [line.strip() for line in (text or "").splitlines() if line.strip()][:limit]


class Conversation(BaseModel):
    """One visitor's chat. Linked to the journey session (cookie) and to the account or lead email only when they are known.
    No IP address is stored."""

    last_at = models.DateTimeField(default=timezone.now, db_index=True)
    session = models.ForeignKey("journey.JourneySession", null=True, blank=True, on_delete=models.SET_NULL, related_name="chats")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="chats")
    lead_email = models.EmailField(blank=True, db_index=True, help_text="Given in the chat to see prices (a lead, as at the journey gate).")
    total_cost_pence = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    message_count = models.PositiveIntegerField(default=0, help_text="Messages from the visitor.")
    browser_hash = models.CharField(max_length=64, blank=True, editable=False, help_text="Hash of the page cookie that started the chat: the id alone cannot continue it.")
    staff_test = models.BooleanField(default=False, db_index=True, help_text="Made in the System test console: left out of the Office list and the figures, counted in spend.")
    ended_by_cap = models.BooleanField(default=False, help_text="The monthly spending cap stopped a reply in this chat.")
    off_topic_count = models.PositiveSmallIntegerField(default=0, help_text="Turns that were off-topic, refused or looked like code.")
    ended_off_topic = models.BooleanField(default=False, help_text="Closed by the server after too many off-topic turns. Flagged in the Office list.")

    class Meta:
        ordering = ["-last_at"]
        indexes = [models.Index(fields=["-last_at"])]

    def __str__(self):
        return f"Chat {str(self.pk)[:8]}"


class Message(BaseModel):
    USER, ASSISTANT = "user", "assistant"
    ROLE_CHOICES = [(USER, "Visitor"), (ASSISTANT, "Spa 99")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    text = models.TextField()
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    cache_write_tokens = models.PositiveIntegerField(default=0)
    cost_pence = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    stop_reason = models.CharField(max_length=30, blank=True)
    flagged_handoff = models.BooleanField(default=False, help_text="The reply ended with the hand-off buttons.")
    offered_email = models.BooleanField(default=False, help_text="The reply asked for an email to show prices.")
    off_topic = models.BooleanField(default=False, help_text="The visitor's message was off-topic (the reply declined).")

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"]), models.Index(fields=["created_at"])]

    def __str__(self):
        return f"{self.role}: {self.text[:40]}"
