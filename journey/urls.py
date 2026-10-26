from django.urls import path

from . import views

app_name = "journey"

urlpatterns = [
    path("state/", views.state, name="state"),
    path("answer/", views.answer, name="answer"),
    path("step/", views.step, name="step"),
    path("result/", views.result, name="result"),
    path("lead/", views.lead, name="lead"),
    path("restart/", views.restart, name="restart"),
]
