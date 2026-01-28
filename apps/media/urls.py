from django.urls import re_path

from . import views

app_name = "media"

urlpatterns = [
    re_path(r"^view/(?P<path>.+)$", views.view_file, name="view_file"),
    re_path(r"^public/(?P<path>.+)$", views.view_public_file, name="view_public_file"),
]
