from django.urls import path

from . import views, views_library as lib

urlpatterns = [
    path("", views.rooms, name="control_rooms"),
    path("schedule/", views.schedule, name="control_schedule"),
    path("screens/", views.screens, name="control_screens"),
    path("library/", lib.library, name="control_library"),
    path("library/assets/", lib.assets, name="control_assets"),
    path("library/assets/upload/", lib.upload, name="control_asset_upload"),
    path("library/assets/<uuid:pk>/update/", lib.asset_update, name="control_asset_update"),
    path("library/assets/<uuid:pk>/duration/", lib.asset_duration, name="control_asset_duration"),
    path("library/assets/<uuid:pk>/delete/", lib.asset_delete, name="control_asset_delete"),
    path("library/playlists/", lib.playlists, name="control_playlists"),
    path("library/playlists/create/", lib.playlist_create, name="control_playlist_create"),
    path("library/playlists/<uuid:pk>/update/", lib.playlist_update, name="control_playlist_update"),
    path("library/playlists/<uuid:pk>/delete/", lib.playlist_delete, name="control_playlist_delete"),
    path("library/playlists/<uuid:pk>/items/add/", lib.item_add, name="control_item_add"),
    path("library/playlists/<uuid:pk>/items/remove/", lib.item_remove, name="control_item_remove"),
    path("library/playlists/<uuid:pk>/items/reorder/", lib.item_reorder, name="control_item_reorder"),
    path("password/", views.ControlPasswordView.as_view(), name="control_password"),
]
