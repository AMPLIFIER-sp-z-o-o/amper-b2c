from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db import models, transaction
from django.utils import timezone

from apps.media.storage import get_active_storage

from .models import DraftChange, DraftSession

SNAPSHOT_SESSION_PREFIX = "snapshot:"


def _normalize_payload(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _get_payload_sections(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return payload.get("form_data", {}), payload.get("temp_files", {})


def _extract_temp_path(info: Any) -> str | None:
    if isinstance(info, dict):
        return info.get("path")
    return info


def get_draft_ttl_minutes() -> int:
    return int(getattr(settings, "DRAFT_PREVIEW_TTL_MINUTES", 15))


def cleanup_expired_drafts() -> None:
    cutoff = timezone.now() - timedelta(minutes=get_draft_ttl_minutes())
    expired = DraftChange.objects.filter(updated_at__lt=cutoff)
    for draft in expired:
        delete_temp_files(draft.payload)
    with transaction.atomic():
        expired.delete()
        # Delete sessions that have no draft_changes left
        # Use a subquery to find sessions with at least one draft change
        sessions_with_drafts = DraftChange.objects.values_list("session_id", flat=True).distinct()
        DraftSession.objects.exclude(id__in=sessions_with_drafts).delete()


def is_session_active(session_key: str) -> bool:
    if not session_key:
        return False
    return Session.objects.filter(session_key=session_key, expire_date__gt=timezone.now()).exists()


def is_snapshot_session(session_key: str | None) -> bool:
    return bool(session_key) and session_key.startswith(SNAPSHOT_SESSION_PREFIX)


def get_or_create_draft_session(user, session_key: str) -> DraftSession:
    draft_session, created = DraftSession.objects.get_or_create(
        session_key=session_key,
        defaults={"user": user, "share_token": uuid4().hex},
    )
    if not created and draft_session.user_id != user.id:
        draft_session.user = user
        draft_session.save(update_fields=["user", "updated_at"])
    return draft_session


def create_snapshot_session(user, drafts: models.QuerySet[DraftChange] | list[DraftChange]) -> DraftSession:
    share_token = uuid4().hex
    snapshot_session_key = f"{SNAPSHOT_SESSION_PREFIX}{uuid4().hex}"
    snapshot_session = DraftSession.objects.create(
        user=user,
        session_key=snapshot_session_key,
        share_token=share_token,
    )

    snapshot_changes = [
        DraftChange(
            session=snapshot_session,
            content_type=draft.content_type,
            object_id=draft.object_id,
            draft_token=draft.draft_token,
            object_repr=draft.object_repr,
            admin_change_url=draft.admin_change_url,
            payload=draft.payload,
        )
        for draft in drafts
    ]

    if snapshot_changes:
        DraftChange.objects.bulk_create(snapshot_changes)

    return snapshot_session


def get_draft_session_by_token(share_token: str) -> DraftSession | None:
    if not share_token:
        return None
    return DraftSession.objects.filter(share_token=share_token).first()


def get_active_drafts_for_session(draft_session: DraftSession) -> models.QuerySet[DraftChange]:
    cleanup_expired_drafts()
    cutoff = timezone.now() - timedelta(minutes=get_draft_ttl_minutes())
    return (
        DraftChange.objects.filter(session=draft_session, updated_at__gte=cutoff)
        .select_related("content_type")
        .order_by("-updated_at")
    )


def build_draft_map(drafts: models.QuerySet[DraftChange]) -> dict[tuple[int, str], DraftChange]:
    draft_map: dict[tuple[int, str], DraftChange] = {}
    for draft in drafts:
        if draft.content_type_id and draft.object_id:
            key = (draft.content_type_id, str(draft.object_id))
            draft_map.setdefault(key, draft)
    return draft_map


def save_temp_upload(upload, session_key: str) -> dict[str, str]:
    storage = get_active_storage()
    ext = Path(upload.name).suffix
    temp_path = f"drafts/{session_key}/{uuid4().hex}{ext}"
    saved_path = storage.save(temp_path, upload)
    return {
        "path": saved_path,
        "url": storage.url(saved_path),
        "name": upload.name,
    }


def delete_temp_files(payload: dict[str, Any] | None) -> None:
    payload = _normalize_payload(payload)
    temp_files = payload.get("temp_files", {})
    if not temp_files or not isinstance(temp_files, dict):
        return

    storage = get_active_storage()
    for info in temp_files.values():
        path = _extract_temp_path(info)
        if not path:
            continue
        try:
            storage.delete(path)
        except Exception:
            continue


def _coerce_field_value(field: models.Field, raw_value: Any) -> Any:
    if isinstance(raw_value, list):
        raw_value = raw_value[-1] if raw_value else None

    if isinstance(raw_value, bool):
        return raw_value

    if raw_value in (None, ""):
        return None if field.null else ""

    try:
        return field.to_python(raw_value)
    except Exception:
        return raw_value


def apply_draft_to_instance(
    instance: models.Model,
    form_data: dict[str, Any],
    temp_files: dict[str, Any] | None = None,
) -> bool:
    fields_by_name = {field.name: field for field in instance._meta.fields}
    changed = False

    temp_files = temp_files or {}
    for field_name, info in temp_files.items():
        field = fields_by_name.get(field_name)
        if not field or not isinstance(field, models.FileField):
            continue
        if isinstance(info, dict):
            temp_path = info.get("path")
        else:
            temp_path = info
        current_name = getattr(getattr(instance, field.name, None), "name", None)
        if temp_path and current_name != temp_path:
            setattr(instance, field.name, temp_path)
            changed = True
        elif temp_path is None and current_name:
            setattr(instance, field.name, None)
            changed = True

    for field_name, raw_value in form_data.items():
        field = fields_by_name.get(field_name)
        if not field:
            continue

        if isinstance(field, models.ManyToManyField):
            continue

        if isinstance(field, models.FileField):
            continue

        if isinstance(field, models.ForeignKey):
            new_value = _coerce_field_value(field, raw_value)
            if getattr(instance, field.attname) != new_value:
                setattr(instance, field.attname, new_value)
                instance.__dict__.pop(field.name, None)
                changed = True
            continue

        new_value = _coerce_field_value(field, raw_value)
        if getattr(instance, field.name) != new_value:
            setattr(instance, field.name, new_value)
            changed = True

    if changed:
        instance._draft_applied = True
    return changed


def _detect_inline_prefixes(form_data: dict[str, Any]) -> set[str]:
    """
    Detect inline form prefixes from form_data.
    Looks for keys like 'links-TOTAL_FORMS', 'sections-TOTAL_FORMS', etc.
    """
    return {key[:-12] for key in form_data if key.endswith("-TOTAL_FORMS")}


def _get_inline_model_for_prefix(
    parent_model: type[models.Model],
    prefix: str,
) -> type[models.Model] | None:
    """
    Find the inline model class for a given prefix by checking ForeignKey relations.
    Matches prefix against related_name or default related names.
    """
    # Get all reverse ForeignKey relations to this model
    for rel in parent_model._meta.get_fields():
        if not isinstance(rel, models.fields.reverse_related.ForeignObjectRel):
            continue
        if not hasattr(rel, "related_model"):
            continue

        related_model = rel.related_model
        related_name = rel.get_accessor_name()

        # Match prefix against related_name (e.g., 'links' matches 'links')
        if related_name == prefix:
            return related_model

        # Also try matching against model name variations
        model_name = related_model._meta.model_name
        if model_name == prefix or f"{model_name}s" == prefix or f"{model_name}_set" == prefix:
            return related_model

    return None


def _resolve_inline_instance(
    inline_model_class: type[models.Model],
    existing_map: dict[str, models.Model],
    item_id: Any,
    allow_missing_existing: bool,
) -> models.Model:
    if item_id and str(item_id) in existing_map:
        instance = existing_map[str(item_id)]
        if not allow_missing_existing:
            return inline_model_class.objects.get(pk=instance.pk)
        return inline_model_class.objects.filter(pk=instance.pk).first() or inline_model_class()
    return inline_model_class()


def _build_inline_items(
    inline_model_class: type[models.Model],
    inline_prefix: str,
    form_data: dict[str, Any],
    existing_items: list[models.Model],
    allow_missing_existing: bool,
) -> list[models.Model]:
    total_forms_key = f"{inline_prefix}-TOTAL_FORMS"
    total_forms = int(form_data.get(total_forms_key, 0))

    if total_forms == 0:
        return existing_items

    existing_map = {str(item.pk): item for item in existing_items if item.pk}
    fields_by_name = {field.name: field for field in inline_model_class._meta.fields}
    skip_field_types = (models.AutoField, models.ForeignKey, models.ManyToManyField)

    result_items: list[models.Model] = []

    for i in range(total_forms):
        prefix = f"{inline_prefix}-{i}"
        item_id = form_data.get(f"{prefix}-id")
        is_deleted = form_data.get(f"{prefix}-DELETE") in (True, "on", "True", "true")

        if is_deleted:
            continue

        instance = _resolve_inline_instance(
            inline_model_class,
            existing_map,
            item_id,
            allow_missing_existing,
        )

        changed = False
        for field_name, field in fields_by_name.items():
            form_key = f"{prefix}-{field_name}"
            if form_key not in form_data:
                continue

            if isinstance(field, skip_field_types):
                continue

            raw_value = form_data[form_key]
            new_value = _coerce_field_value(field, raw_value)

            if getattr(instance, field_name, None) != new_value:
                setattr(instance, field_name, new_value)
                changed = True

        if changed:
            instance._draft_applied = True

        result_items.append(instance)

    if hasattr(inline_model_class, "order"):
        result_items.sort(key=lambda x: (getattr(x, "order", 0) or 0, getattr(x, "pk", 0) or 0))

    return result_items


def _apply_inline_draft_to_list(
    inline_model_class: type[models.Model],
    inline_prefix: str,
    form_data: dict[str, Any],
    existing_items: list[models.Model],
) -> list[models.Model]:
    """
    Apply draft changes to a list of inline items.
    Automatically handles additions, modifications, and deletions.
    """
    return _build_inline_items(
        inline_model_class=inline_model_class,
        inline_prefix=inline_prefix,
        form_data=form_data,
        existing_items=existing_items,
        allow_missing_existing=True,
    )


def apply_drafts_to_context(context: Any, drafts_map: dict[tuple[int, str], DraftChange]) -> Any:
    """
    Apply draft changes to all objects in a template context.
    Automatically handles both main model fields AND inline relations.
    """
    visited: set[int] = set()
    # Track which inline lists we've already processed (by their parent draft)
    processed_inlines: dict[int, dict[str, dict[str, Any]]] = {}

    if context is None:
        return context

    if hasattr(context, "dicts"):
        for ctx in context.dicts:
            apply_drafts_to_context(ctx, drafts_map)
        return context

    def _get_processed_inlines_for_draft(draft: DraftChange) -> dict[str, dict[str, Any]]:
        """Get or compute processed inline items for a draft."""
        draft_id = id(draft)
        if draft_id in processed_inlines:
            return processed_inlines[draft_id]

        result: dict[str, dict[str, Any]] = {}
        payload = _normalize_payload(draft.payload)
        form_data, _ = _get_payload_sections(payload)

        if not draft.content_type_id:
            processed_inlines[draft_id] = result
            return result

        parent_model = draft.content_type.model_class()
        if not parent_model:
            processed_inlines[draft_id] = result
            return result

        # Detect all inline prefixes in this draft
        prefixes = _detect_inline_prefixes(form_data)

        for prefix in prefixes:
            inline_model = _get_inline_model_for_prefix(parent_model, prefix)
            if inline_model:
                result[prefix] = {
                    "model": inline_model,
                    "form_data": form_data,
                }

        processed_inlines[draft_id] = result
        return result

    def _apply(obj: Any) -> Any:
        obj_id = id(obj)
        if obj_id in visited:
            return obj
        visited.add(obj_id)

        if isinstance(obj, models.Model):
            content_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
            draft = drafts_map.get((content_type.pk, str(obj.pk)))
            if draft:
                payload = _normalize_payload(draft.payload)
                form_data, temp_files = _get_payload_sections(payload)
                apply_draft_to_instance(obj, form_data, temp_files)
            return obj

        if isinstance(obj, models.QuerySet):
            for item in obj:
                _apply(item)
            return obj

        if isinstance(obj, dict):
            for key, value in obj.items():
                obj[key] = _apply(value)
            return obj

        if isinstance(obj, (list, tuple, set)):
            # Check if this is a list of model instances that might be inlines
            items_list = list(obj)
            if items_list and isinstance(items_list[0], models.Model):
                # Try to find if these items are inlines of a parent with a draft
                first_item = items_list[0]
                inline_model = type(first_item)

                # Find ForeignKey fields that point to models with drafts
                for field in inline_model._meta.fields:
                    if not isinstance(field, models.ForeignKey):
                        continue

                    parent_model = field.related_model
                    parent_ct = ContentType.objects.get_for_model(parent_model)

                    # Check all items for their parent
                    for item in items_list:
                        parent_id = getattr(item, field.attname, None)
                        if not parent_id:
                            continue

                        draft = drafts_map.get((parent_ct.pk, str(parent_id)))
                        if not draft:
                            continue

                        # Found a draft for the parent! Get inline info
                        inline_info = _get_processed_inlines_for_draft(draft)

                        # Find the matching prefix for this inline model
                        for prefix, info in inline_info.items():
                            if info["model"] == inline_model:
                                # Apply draft changes to the entire list
                                modified_items = _apply_inline_draft_to_list(
                                    inline_model,
                                    prefix,
                                    info["form_data"],
                                    items_list,
                                )
                                if isinstance(obj, tuple):
                                    return tuple(modified_items)
                                if isinstance(obj, set):
                                    return set(modified_items)
                                return modified_items

            # Default: process each item individually
            items = [_apply(item) for item in obj]
            if isinstance(obj, tuple):
                return tuple(items)
            if isinstance(obj, set):
                return set(items)
            return items

        return obj

    return _apply(context)


def get_new_draft_instance(request: Any, model_class: type[models.Model]) -> models.Model | None:
    """
    Get a new (unsaved) instance populated with draft data.
    Looks for drafts where object_id is empty (new records).

    Args:
        request: HttpRequest with draft_changes attribute
        model_class: The Django model class

    Returns:
        Model instance with draft data applied, or None if no draft found
    """
    draft_changes = getattr(request, "draft_changes", [])
    if not draft_changes:
        return None

    content_type = ContentType.objects.get_for_model(model_class)

    for draft in draft_changes:
        # New records have no object_id or object_id == ""
        if draft.content_type_id == content_type.id and not draft.object_id:
            instance = model_class()
            payload = _normalize_payload(draft.payload)
            form_data, temp_files = _get_payload_sections(payload)
            apply_draft_to_instance(instance, form_data, temp_files)
            return instance

    return None


def compute_draft_diff(draft: DraftChange) -> list[dict[str, Any]]:
    payload = _normalize_payload(draft.payload)
    form_data, temp_files = _get_payload_sections(payload)
    if not draft.content_type_id:
        return []

    model_class = draft.content_type.model_class()
    if not model_class:
        return []

    instance = None
    if draft.object_id:
        instance = model_class.objects.filter(pk=draft.object_id).first()

    fields_by_name = {field.name: field for field in model_class._meta.fields}
    diffs: list[dict[str, Any]] = []

    for field_name, raw_value in form_data.items():
        field = fields_by_name.get(field_name)
        if not field:
            continue
        if isinstance(field, models.ManyToManyField):
            continue

        if isinstance(field, models.FileField):
            info = temp_files.get(field_name)
            if info:
                new_value = info.get("name") if isinstance(info, dict) else info
                old_value = getattr(getattr(instance, field.name, None), "name", None) if instance else None
                diffs.append(
                    {
                        "name": field.verbose_name,
                        "field": field_name,
                        "old": old_value,
                        "new": new_value,
                    }
                )
            continue

        new_value = _coerce_field_value(field, raw_value)
        if isinstance(field, models.ForeignKey):
            old_value = getattr(instance, field.attname, None) if instance else None
        else:
            old_value = getattr(instance, field.name, None) if instance else None

        if instance is None or old_value != new_value:
            diffs.append(
                {
                    "name": field.verbose_name,
                    "field": field_name,
                    "old": old_value,
                    "new": new_value,
                }
            )

    return diffs


def apply_inline_drafts(
    parent_model_class: type[models.Model],
    parent_object_id: str | int,
    inline_model_class: type[models.Model],
    inline_prefix: str,
    existing_items: list[models.Model],
    draft_changes: list[DraftChange],
) -> list[models.Model]:
    """
    Apply draft changes to inline items (e.g., BottomBarLink, FooterSectionLink).

    Args:
        parent_model_class: The parent model class (e.g., BottomBar)
        parent_object_id: The ID of the parent object
        inline_model_class: The inline model class (e.g., BottomBarLink)
        inline_prefix: The form prefix for inlines (e.g., "links")
        existing_items: List of existing inline items from database
        draft_changes: List of draft changes from request

    Returns:
        List of inline items with draft changes applied
    """
    if not draft_changes:
        return existing_items

    parent_content_type = ContentType.objects.get_for_model(parent_model_class)

    # Find the draft for the parent object
    draft = None
    for dc in draft_changes:
        if dc.content_type_id == parent_content_type.id and str(dc.object_id) == str(parent_object_id):
            draft = dc
            break

    if not draft:
        return existing_items

    payload = _normalize_payload(draft.payload)
    form_data, _ = _get_payload_sections(payload)
    return _build_inline_items(
        inline_model_class=inline_model_class,
        inline_prefix=inline_prefix,
        form_data=form_data,
        existing_items=existing_items,
        allow_missing_existing=False,
    )
