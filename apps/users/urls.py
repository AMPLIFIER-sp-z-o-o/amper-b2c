from django.urls import path

from . import views

app_name = "users"
urlpatterns = [
    path("profile/", views.profile, name="user_profile"),
    path("account/", views.account_details, name="account_details"),
    path("account/addresses/", views.account_addresses, name="account_addresses"),
    path("account/orders/", views.account_orders, name="account_orders"),
    path("account/delete/", views.account_delete, name="account_delete"),
    path("account/email/change/", views.account_request_email_change, name="account_request_email_change"),
    path("account/email/cancel/", views.account_cancel_email_change, name="account_cancel_email_change"),
    path("account/email/resend/", views.account_resend_email_change, name="account_resend_email_change"),
    path("account/email/confirm/<str:token>/", views.account_confirm_email_change, name="account_confirm_email_change"),
    path("api-keys/create/", views.create_api_key, name="create_api_key"),
    path("api-keys/revoke/", views.revoke_api_key, name="revoke_api_key"),
    path("set-timezone/", views.set_timezone, name="set_timezone"),
    path("resend-verification-email/", views.resend_verification_email, name="resend_verification_email"),
]
