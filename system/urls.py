from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="system_dashboard"),
    path("unlock/", views.unlock, name="system_unlock"),
    path("lock/", views.lock, name="system_lock"),
    path("changes/", views.change_log, name="system_changes"),
    path("changes/<uuid:pk>/undo/", views.undo, name="system_undo"),
    path("emails/", views.emails, name="system_emails"),
    path("settings/", views.site_settings, name="system_settings"),
    path("team/", views.team, name="system_team"),
    path("team/<uuid:pk>/roles/", views.team_roles, name="system_team_roles"),
    path("team/<uuid:pk>/active/", views.team_active, name="system_team_active"),
]
