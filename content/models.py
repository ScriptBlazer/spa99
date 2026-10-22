"""Editable site copy and images. A Page holds Sections; templates ask for a section by page key + section key."""
from django.db import models
from simple_history.models import HistoricalRecords

from common.models import BaseModel


class Page(BaseModel):
    key = models.SlugField(unique=True, help_text="home, spa, memberships, gold, book, visit, privacy, terms ...")
    title = models.CharField(max_length=120)
    meta_description = models.CharField(max_length=300, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    history = HistoricalRecords()

    class Meta:
        ordering = ["order", "key"]

    def __str__(self):
        return self.title


def section_image_path(instance, filename):
    return f"content/{instance.page.key}/{filename}"


class Section(BaseModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="sections")
    key = models.SlugField(help_text="Stable name the template asks for, e.g. hero.")
    heading = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    image = models.FileField(upload_to=section_image_path, blank=True)  # default storage: S3 on live
    image_alt = models.CharField(max_length=200, blank=True)
    cta_label = models.CharField(max_length=60, blank=True)
    cta_url = models.CharField(max_length=300, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    visible = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["page__order", "order", "key"]
        constraints = [models.UniqueConstraint(fields=["page", "key"], name="content_section_unique_key_per_page")]

    def __str__(self):
        return f"{self.page.key}/{self.key}"
