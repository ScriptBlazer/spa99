"""The "Ask us" chat (docs/features/ai-chat.md): saved conversations (deleted after 90 days) and the FAQ Moishe edits in System.

Conversation and Message have no django-simple-history on purpose (one line): they are append-only logs that are deleted after
90 days, and a history table would copy the chat text for ever. The FAQ is ordinary editable data, so it has history (the change log)."""
from django.conf import settings
from django.db import models
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
