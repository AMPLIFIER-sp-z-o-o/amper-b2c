from django.urls import path

from . import views

app_name = "users"
urlpatterns = [
    path("profile/", views.profile, name="user_profile"),
    path("profile/upload-image/", views.upload_profile_image, name="upload_profile_image"),
    path("api-keys/create/", views.create_api_key, name="create_api_key"),
    path("api-keys/revoke/", views.revoke_api_key, name="revoke_api_key"),
    path("set-timezone/", views.set_timezone, name="set_timezone"),
    path("resend-verification-email/", views.resend_verification_email, name="resend_verification_email"),
]
