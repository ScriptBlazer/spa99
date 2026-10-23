from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="office_dashboard"),
    path("dashboard.json", views.dashboard_json, name="office_dashboard_json"),
    path("analytics/", views.analytics, name="office_analytics"),
    path("analytics/data/", views.analytics_data, name="office_analytics_data"),
    path("analytics/pages/", views.analytics_pages, name="office_analytics_pages"),
    path("people/", views.people, name="office_people"),
    path("people/export.csv", views.people_csv, name="office_people_csv"),
    path("people/<uuid:pk>/", views.person, name="office_person"),
    path("people/<uuid:pk>/export/", views.person_export, name="office_person_export"),
    path("people/<uuid:pk>/delete/", views.person_delete, name="office_person_delete"),
    path("gold/", views.gold, name="office_gold"),
    path("gold/<uuid:pk>/", views.gold_application, name="office_gold_application"),
    path("gold/<uuid:pk>/approve/confirm/", views.gold_approve_confirm, name="office_gold_approve_confirm"),
    path("gold/<uuid:pk>/approve/", views.gold_approve, name="office_gold_approve"),
    path("gold/<uuid:pk>/resend/", views.gold_resend, name="office_gold_resend"),
    path("gold/<uuid:pk>/decline/", views.gold_decline, name="office_gold_decline"),
]
