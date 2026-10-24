from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import MediaAsset, Playlist


@admin.register(MediaAsset)
class MediaAssetAdmin(SimpleHistoryAdmin):
    list_display = ("title", "kind", "size_bytes", "duration_seconds", "uploaded_by", "created_at")
    list_filter = ("kind",)
    search_fields = ("title",)


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "created_by", "created_at")
