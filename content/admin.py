from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Page, Section


class SectionInline(admin.StackedInline):
    model = Section
    extra = 0
    fields = ("key", "heading", "body", "image", "image_alt", "cta_label", "cta_url", "order", "visible")


@admin.register(Page)
class PageAdmin(SimpleHistoryAdmin):
    list_display = ("key", "title", "order")
    inlines = [SectionInline]


@admin.register(Section)
class SectionAdmin(SimpleHistoryAdmin):
    list_display = ("page", "key", "heading", "order", "visible")
    list_filter = ("page", "visible")
    search_fields = ("key", "heading", "body")
