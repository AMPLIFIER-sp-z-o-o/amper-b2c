import json
from uuid import uuid4
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from hijack.views import AcquireUserView

from .draft_preview_links import build_preview_links
from .draft_utils import (
    SNAPSHOT_SESSION_PREFIX,
    create_snapshot_session,
    delete_temp_files,
    get_active_drafts_for_session,
    get_or_create_draft_session,
    save_temp_upload,
)
from .forms import HijackUserForm
from .models import DraftChange, DraftSession


def _append_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params[key] = value
    new_query = urlencode(query_params)
    return urlunparse(parsed._replace(query=new_query))


def _parse_json_payload(request) -> dict | None:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _cleanup_stale_drafts(
    *,
    content_type: ContentType | None,
    object_id: str | None,
    session,
    draft_token: str,
) -> None:
    if not content_type or not object_id:
        return
    stale_drafts = DraftChange.objects.filter(content_type=content_type, object_id=str(object_id)).exclude(
        session=session, draft_token=draft_token
    )
    stale_drafts = stale_drafts.exclude(session__session_key__startswith=SNAPSHOT_SESSION_PREFIX)
    for draft in stale_drafts:
        delete_temp_files(draft.payload)
    stale_drafts.delete()


@user_passes_test(lambda u: u.is_superuser, login_url="/404")
@staff_member_required
def hijack_user(request):
    form = HijackUserForm()
    return render(
        request,
        "support/hijack_user.html",
        {
            "active_tab": "support",
            "form": form,
            "redirect_url": settings.LOGIN_REDIRECT_URL,
        },
    )


@staff_member_required
def open_hijack_in_new_tab(request, user_pk: int):
    if request.method == "POST":
        next_url = request.POST.get("next") or "/"
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = "/"

        post_data = request.POST.copy()
        post_data["user_pk"] = str(user_pk)
        post_data["next"] = next_url
        request._post = post_data
        return AcquireUserView.as_view()(request)

    next_url = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = "/"

    tab_id = uuid4().hex
    scoped_next = _append_query_param(next_url, "__tab", tab_id)

    bridge_action = _append_query_param(reverse("support:hijack_open_tab", args=[user_pk]), "__tab", tab_id)

    return render(
        request,
        "support/hijack_open_tab.html",
        {
            "hijack_user_pk": user_pk,
            "bridge_action_url": bridge_action,
            "hijack_next": scoped_next,
        },
    )


@staff_member_required
@require_POST
def save_admin_draft(request):
    payload = _parse_json_payload(request)
    if payload is None:
        return HttpResponseBadRequest("Invalid JSON")

    app_label = payload.get("app_label")
    model_name = payload.get("model_name")
    draft_token = payload.get("draft_token")
    if not app_label or not model_name or not draft_token:
        return HttpResponseBadRequest("Missing draft metadata")

    content_type = ContentType.objects.filter(app_label=app_label, model=model_name).first()
    object_id = payload.get("object_id") or None

    if not request.session.session_key:
        request.session.save()
    draft_session = get_or_create_draft_session(request.user, request.session.session_key)

    form_data = payload.get("form_data", {})
    incoming_temp_files = payload.get("temp_files", {})
    merged_temp_files = {}
    existing_draft = DraftChange.objects.filter(session=draft_session, draft_token=draft_token).first()
    if existing_draft and isinstance(existing_draft.payload, dict):
        merged_temp_files.update(existing_draft.payload.get("temp_files", {}))

    if isinstance(incoming_temp_files, dict):
        for key, value in incoming_temp_files.items():
            if value:
                merged_temp_files[key] = value
            else:
                merged_temp_files.pop(key, None)
    draft_payload = {
        "form_data": form_data,
        "temp_files": merged_temp_files,
        "page_url": payload.get("page_url", ""),
        "form_action": payload.get("form_action", ""),
    }

    _cleanup_stale_drafts(
        content_type=content_type,
        object_id=object_id,
        session=draft_session,
        draft_token=draft_token,
    )

    DraftChange.objects.update_or_create(
        session=draft_session,
        draft_token=draft_token,
        defaults={
            "content_type": content_type,
            "object_id": object_id,
            "object_repr": payload.get("object_repr", ""),
            "admin_change_url": payload.get("admin_change_url", ""),
            "payload": draft_payload,
        },
    )

    return JsonResponse({"ok": True})


@staff_member_required
@require_POST
def clear_admin_draft(request):
    payload = _parse_json_payload(request)
    if payload is None:
        return HttpResponseBadRequest("Invalid JSON")

    draft_token = payload.get("draft_token")
    if not draft_token:
        return HttpResponseBadRequest("Missing draft token")

    if not request.session.session_key:
        return JsonResponse({"ok": True})

    draft = DraftChange.objects.filter(
        session__session_key=request.session.session_key, draft_token=draft_token
    ).first()
    if draft:
        delete_temp_files(draft.payload)
        draft.delete()
    return JsonResponse({"ok": True})


@staff_member_required
@require_POST
def upload_admin_draft_file(request):
    draft_token = request.POST.get("draft_token")
    field_name = request.POST.get("field_name")
    app_label = request.POST.get("app_label")
    model_name = request.POST.get("model_name")
    object_id = request.POST.get("object_id") or None
    object_repr = request.POST.get("object_repr", "")
    admin_change_url = request.POST.get("admin_change_url", "")
    upload = request.FILES.get("file")

    if not draft_token or not field_name or not app_label or not model_name or not upload:
        return HttpResponseBadRequest("Missing upload metadata")

    if not request.session.session_key:
        request.session.save()
    draft_session = get_or_create_draft_session(request.user, request.session.session_key)
    content_type = ContentType.objects.filter(app_label=app_label, model=model_name).first()

    temp_info = save_temp_upload(upload, draft_session.session_key)

    existing_draft = DraftChange.objects.filter(session=draft_session, draft_token=draft_token).first()
    payload = existing_draft.payload if existing_draft and isinstance(existing_draft.payload, dict) else {}
    temp_files = payload.get("temp_files", {}) if isinstance(payload, dict) else {}
    temp_files[field_name] = temp_info

    draft_payload = {
        "form_data": payload.get("form_data", {}),
        "temp_files": temp_files,
        "page_url": payload.get("page_url", ""),
        "form_action": payload.get("form_action", ""),
    }

    _cleanup_stale_drafts(
        content_type=content_type,
        object_id=object_id,
        session=draft_session,
        draft_token=draft_token,
    )

    DraftChange.objects.update_or_create(
        session=draft_session,
        draft_token=draft_token,
        defaults={
            "content_type": content_type,
            "object_id": object_id,
            "object_repr": object_repr,
            "admin_change_url": admin_change_url,
            "payload": draft_payload,
        },
    )

    return JsonResponse({"ok": True, "file": temp_info})


@staff_member_required
def enable_draft_preview(request):
    if not request.session.session_key:
        request.session.save()
    draft_session = get_or_create_draft_session(request.user, request.session.session_key)
    snapshot_session = create_snapshot_session(request.user, list(get_active_drafts_for_session(draft_session)))
    request.session["draft_preview_token"] = snapshot_session.share_token
    request.session["draft_preview_enabled"] = True
    request.session.modified = True
    next_url = request.GET.get("next") or reverse("web:home")
    preview_url = _append_query_param(next_url, "preview_token", snapshot_session.share_token)
    return redirect(preview_url)


@staff_member_required
def draft_preview_links(request):
    draft_links = []
    admin_change_url = request.GET.get("admin_change_url", "")
    session_key = getattr(getattr(request, "session", None), "session_key", None)
    if session_key:
        draft_session = DraftSession.objects.filter(session_key=session_key).first()
        if draft_session:
            drafts = get_active_drafts_for_session(draft_session)
            if admin_change_url:
                drafts = drafts.filter(admin_change_url=admin_change_url)
            if drafts:
                draft_links = build_preview_links(drafts)

    html = render_to_string(
        "admin/components/draft_preview_links.html",
        {"draft_preview_links": draft_links},
        request=request,
    )
    return HttpResponse(html)


@staff_member_required
def disable_draft_preview(request):
    request.session["draft_preview_enabled"] = False
    request.session.pop("draft_preview_token", None)
    request.session.modified = True
    next_url = request.GET.get("next") or reverse("web:home")
    return redirect(next_url)


def generic_draft_preview(request, app_label: str, model_name: str):
    """
    Generic draft preview for new (unsaved) records.
    Automatically renders a preview for any model with get_absolute_url().
    """
    from django.http import Http404

    from .draft_utils import get_new_draft_instance

    if not getattr(request, "draft_preview_enabled", False):
        raise Http404("Draft preview not enabled")

    content_type = ContentType.objects.filter(app_label=app_label, model=model_name).first()
    if not content_type:
        raise Http404(f"Model {app_label}.{model_name} not found")

    model_class = content_type.model_class()
    if not model_class:
        raise Http404(f"Model class for {app_label}.{model_name} not found")

    instance = get_new_draft_instance(request, model_class)
    if not instance:
        raise Http404(f"No draft found for {app_label}.{model_name}")

    # Resolve FK relations
    for field in model_class._meta.get_fields():
        if hasattr(field, "related_model") and field.related_model and hasattr(field, "attname"):
            fk_id = getattr(instance, field.attname, None)
            if fk_id and not getattr(instance, field.name, None):
                try:
                    setattr(instance, field.name, field.related_model.objects.filter(pk=fk_id).first())
                except Exception:
                    pass

    verbose_name = model_class._meta.verbose_name.title()
    instance_name = str(instance) or f"New {verbose_name}"

    context = {
        "object": instance,
        "instance": instance,
        "model_name": verbose_name,
        "page_title": instance_name,
        "is_draft_preview": True,
        "draft_banner": {
            "label": "DRAFT",
            "message": f"New {verbose_name} - not yet saved",
            "classes": "border-amber-400 bg-amber-100 text-amber-900"
            if not request.user.is_superuser
            else "border-amber-600 bg-amber-700 text-amber-100",
        },
    }

    # Add model-specific context variable (e.g., "dynamicpage" -> "page")
    # This matches what detail templates typically expect
    model_lower = model_class._meta.model_name
    context[model_lower] = instance

    # Common pattern: templates often use abbreviated names (e.g., "page" for "dynamicpage")
    if model_lower.endswith("page"):
        context["page"] = instance
    elif model_lower.endswith("section"):
        context["section"] = instance
    elif model_lower.endswith("banner"):
        context["banner"] = instance

    # Try to find a detail template for this model
    template_candidates = [
        f"web/{model_class._meta.model_name}s/detail.html",
        f"web/{app_label}/{model_class._meta.model_name}_detail.html",
        f"{app_label}/{model_class._meta.model_name}_detail.html",
    ]

    from django.template import TemplateDoesNotExist
    from django.template.loader import get_template

    for template_name in template_candidates:
        try:
            get_template(template_name)
            return render(request, template_name, context)
        except TemplateDoesNotExist:
            continue

    # No template found - return 404
    raise Http404(f"No detail template found for {app_label}.{model_name}")
