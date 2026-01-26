from django.urls import path, re_path

from . import views

app_name = "media"

urlpatterns = [

    re_path(r"^view/(?P<path>.+)$", views.view_file, name="view_file"),
]
