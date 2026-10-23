"""Public-site account routes (not included on the Control host)."""
from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/sent/", views.register_sent, name="register_sent"),
    path("register/check-email/", views.check_email, name="check_email"),
    path("verify/resend/", views.resend_verification, name="resend_verification"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset/<str:uidb64>/<str:token>/", views.reset_password, name="reset_password"),
    path("account/", views.account, name="account"),
    path("account/book/", views.account_book, name="account_book"),
    path("account/membership/", views.account_membership, name="account_membership"),
    path("account/you/", views.account_you, name="account_you"),
    path("account/you/password/", views.ChangePasswordView.as_view(), name="password_change"),
    path("account/password/", views.password_change_old, name="password_change_old"),  # the old address, kept
    path("account/emails/", views.account_emails, name="account_emails"),
    path("account/interest/", views.account_interest, name="account_interest"),
    path("account/export/", views.account_export, name="account_export"),
    path("account/delete/", views.account_delete, name="account_delete"),
]
