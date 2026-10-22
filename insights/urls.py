from django.urls import path

from . import views

app_name = "insights"

urlpatterns = [
    path("summary/", views.summary, name="summary"),
]
