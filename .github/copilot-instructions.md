# Copilot instructions for AMPER-B2C

## Architecture & Data Flow

- **Django monolith** in `amplifier/` with feature apps in `apps/` (catalog, web, users, api, support, media, homepage).
- **URL composition**: Routes assembled in [amplifier/urls.py](../amplifier/urls.py); each app exposes its own `urls.py`.
- **Templates**: Server-rendered Jinja-style templates in `templates/`; base layout at [templates/web/base.html](../templates/web/base.html).
- **Frontend pipeline**: Vite builds `assets/` → `static/`; templates load via `{% vite_asset %}` tags. Tailwind + Flowbite for styling.
- **HTMX enabled**: Middleware + `hx-headers` in body; use HTMX patterns for partial updates.
- **API layer**: DRF in `apps/api/`; hybrid permission `IsAuthenticatedOrHasUserAPIKey` for session/API key auth (see [apps/api/permissions.py](../apps/api/permissions.py)).

## Model Patterns & Base Classes

- **Always extend `BaseModel`** from [apps/utils/models.py](../apps/utils/models.py) – provides `created_at`/`updated_at` timestamps.
- **Singleton models** use `SingletonModel` base class with `get_settings()` classmethod (e.g., `SiteSettings`, `Footer`, `BottomBar`).
- **File storage**: Use `DynamicMediaStorage()` for ImageField/FileField to support local/S3 switching (see [apps/media/storage.py](../apps/media/storage.py)).
- **CKEditor rich text**: Use `CKEditor5Field(config_name="extends")` for product descriptions.
- **Auto-slugs**: Use `AutoSlugField(populate_from="name", unique=True, always_update=False)` from django-autoslug.

## Admin Patterns (Django Unfold)

- Admin uses **django-unfold** – import from `unfold.admin` (ModelAdmin, TabularInline, StackedInline).
- **Image previews**: Use `make_image_preview_html()` from [apps/utils/admin_utils.py](../apps/utils/admin_utils.py) for consistent thumbnails.
- **Media Library Source Links**: Models using `DynamicMediaStorage` are automatically tracked. To enable "Source" links in the Media Library, the model MUST be registered in `admin.py`. For inlines, use a hidden admin: `has_module_permission = lambda self, r: False`.
- **Price formatting**: Emit `<span data-price="..." data-currency="...">` for JS-based Intl.NumberFormat (see [static/js/admin_custom.js](../static/js/admin_custom.js)).
- **Import/Export**: Use `ImportExportModelAdmin` mixin with `ImportForm`/`ExportForm` from unfold.contrib.
- For file inputs needing custom preview, add `data-product-image-upload="true"` attribute.

## Draft Preview System

- **Automatic autosave**: Admin forms auto-save drafts to session via JS in [static/js/admin_custom.js](../static/js/admin_custom.js).
- **Zero config required**: Works for all admin-registered models including inlines (BottomBarLink, FooterSection, etc.).
- **Preview middleware**: `DraftPreviewMiddleware` applies drafts when `?preview_token=` is in URL.
- **Key utilities** in [apps/support/draft_utils.py](../apps/support/draft_utils.py):
  - `apply_draft_to_instance(instance, form_data, temp_files)` – mutates model instance
  - `apply_drafts_to_context(context, drafts_map)` – applies drafts to template context
  - `get_new_draft_instance(request, model_class)` – creates unsaved instance with draft data
- **Custom preview routes**: Add before slug routes if model has custom preview needs.

## Dev Workflows

| Task                | Command                                              |
| ------------------- | ---------------------------------------------------- |
| Bootstrap project   | `make init`                                          |
| Run dev servers     | `make dev` (Django + Vite)                           |
| Django commands     | `uv run manage.py <cmd>` or `make manage ARGS='...'` |
| Run tests           | `make test` or `make test ARGS='apps.web.tests...'`  |
| Format/lint         | `make ruff` (Ruff formatter + linter)                |
| Reset database      | `make reset-db` (drop + recreate + migrate)          |
| Update translations | `make translations`                                  |
| Celery worker       | `make celery`                                        |

**Superuser credentials**: `admin@example.com` / `admin`

## Environment & Integrations

- **Config**: `.env` via django-environ; defaults: Postgres port 7432, Redis port 7379.
- **Docker services**: `docker-compose.yml` runs Postgres + Redis containers.
- **Celery**: Redis broker; tasks auto-discovered; schedules in `SCHEDULED_TASKS` dict.
- **Media storage**: Configurable local/S3 via `MediaStorageSettings` model – storage cache clears on save.
- **Auth**: Custom `CustomUser` model; allauth adapters in [apps/users/adapter.py](../apps/users/adapter.py).

## Context Processors

Global template context provided by [apps/web/context_processors.py](../apps/web/context_processors.py):

- `project_meta` – SEO metadata from SiteSettings
- `top_bar`, `footer`, `bottom_bar` – site chrome configuration
- `site_currency` – for price display formatting

## Code Conventions

- Models: Extend `BaseModel`, use `_("...")` for translatable strings, define `__str__` and `get_absolute_url()`.
- Admin: Use Unfold components, readonly computed fields with `@admin.display(description=_(...))`.
- Views: Add to app's `urls.py`, use `reverse("app:view_name")` for URL generation.
- Templates: Extend `web/base.html`, use Flowbite components, include HTMX attributes for interactivity.
