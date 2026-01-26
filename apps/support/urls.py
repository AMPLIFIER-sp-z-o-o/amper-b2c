from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("", views.hijack_user, name="hijack_user"),
    path("drafts/save/", views.save_admin_draft, name="draft_save"),
    path("drafts/clear/", views.clear_admin_draft, name="draft_clear"),
    path("drafts/upload/", views.upload_admin_draft_file, name="draft_upload"),
    path("drafts/preview-links/", views.draft_preview_links, name="draft_preview_links"),
    path("drafts/preview/enable/", views.enable_draft_preview, name="draft_preview_enable"),
    path("drafts/preview/disable/", views.disable_draft_preview, name="draft_preview_disable"),
    # Generic draft preview for any model - used for new (unsaved) records
    path("drafts/preview/<str:app_label>/<str:model_name>/", views.generic_draft_preview, name="generic_draft_preview"),
]
