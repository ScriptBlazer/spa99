from django.db import models


class LinkClickDay(models.Model):
    """Aggregate click counts for a short link (the WhatsApp link): one row per link, London day and source. No IP, no browser,
    no person: only a count (UK GDPR: nothing personal is stored per click)."""

    key = models.CharField(max_length=30)
    day = models.DateField()
    source = models.CharField(max_length=200, default="direct")
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "day", "source"], name="pages_linkclickday_unique")]
        indexes = [models.Index(fields=["key", "day"])]

    def __str__(self):
        return f"{self.key} {self.day} {self.source}: {self.count}"
