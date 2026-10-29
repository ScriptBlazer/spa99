from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("the-spa/", views.spa, name="spa"),
    path("tour/", views.tour, name="tour"),
    path("tour/<slug:slug>/", views.tour, name="tour_room"),
    path("memberships/", views.memberships, name="memberships"),
    path("gold-card/", views.gold_card, name="gold_card"),
    path("gold-card/apply/", views.gold_apply, name="gold_apply"),
    path("gold-card/apply/<slug:slug>/", views.gold_apply, name="gold_apply_step"),
    path("book/", views.book, name="book"),
    path("visit/", views.visit, name="visit"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("journey/", views.journey, name="journey"),
    path("journey/<slug:slug>/", views.journey, name="journey_page"),
    path("whatsapp/", views.whatsapp, name="whatsapp"),
    path("example-link/", views.example_link, name="example_link"),  # the placeholder link in email previews
    path("robots.txt", views.robots, name="robots"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
]
