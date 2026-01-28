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
| Run dev servers     | `make dev` (Django + Vite) - **ONLY use this command to start the server. [Do not use this command unless told to.] Do not use manage.py runserver. Use only make dev to start the server**  |
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

## UI Components & Styling

### Price Formatting

Always use **Polish locale (pl-PL)** for price formatting to display values correctly as "6,99 zł" instead of "PLN 6.99":

```javascript
// Correct format
new Intl.NumberFormat('pl-PL', { style: 'currency', currency: 'PLN' }).format(price)
// Result: "6,99 zł"

// WRONG - do NOT use
new Intl.NumberFormat('en-US', { style: 'currency', currency: 'PLN' }).format(price)
// Result: "PLN 6.99"
```

In templates, use the `site_currency` context variable for dynamic currency support.

### Custom CSS Compatibility

Every new component or page section MUST be designed to support the **Custom CSS** functionality (managed in Site Settings). To enable granular styling via the admin:

- **Unique IDs**: Use a unique ID for the main container of each component, typically incorporating the database ID (e.g., `id="product-section-{{ section.id }}"`).
- **Semantic Classes**: Add descriptive, component-specific classes (e.g., `class="homepage-section section-product-list"`).
- **Predictable Selectors**: Ensure that all sub-elements can be easily targeted via CSS nesting starting from the component's unique ID or class.

Example pattern from `homepage_product_section.html`:
```html
<section id="product-section-{{ section.id }}" class="homepage-section section-product-list ...">
    <!-- Component content -->
</section>
```

## Change Validation & Testing

### When tests ARE required

Tests should be created for changes that:
- Modify **business logic** (e.g., calculations, validations, workflows)
- Change **behavior of existing functions** or API endpoints
- Add **new endpoints** or views
- Modify **data models** or relationships between them
- Introduce **edge case handling** or error handling

### When tests are NOT required

Tests can be skipped for purely cosmetic/configuration changes:
- **CSS style** changes (colors, margins, fonts)
- Updates to **static text** or translations
- **HTML template** modifications without logic (layout, CSS classes)
- **Admin configuration** changes (field ordering, labels)
- **Documentation** or comment updates

### Testing Strategy & Best Practices

- **Edge Case First**: Identify and write tests for all possible edge cases **before** or during the implementation.
- **Backend Best Practices**:
    - Always test **Permission & Authorization**: verify that unauthorized users receive 403 or redirect to login.
    - Test **Data Integrity**: verify how the system handles empty values, invalid formats, and duplicate entries.
    - For **HTMX views**, verify that the correct partial templates are rendered and required HTMX headers are present.
- **Browser Best Practices**:
    - Test across different **viewport sizes** (Mobile vs Desktop).
    - Verify **UI Feedback**: ensure loading states, error messages, and success notifications are visible and correct.
    - Check accessibility and keyboard navigation for interactive elements.

### Testing Tools

1. **Backend tests** (when required):
   - Use **pytest** + **pytest-django**.
   - Use `@pytest.mark.django_db` for functional tests or classes that don't inherit from `TestCase` and need database access.
   - Include positive and negative test scenarios.
   - Run via `make test`.

2. **Browser tests** (always required for UI changes):
   - Visual verification using **Chrome MCP** tool.
   - Test interactions (clicks, forms, HTMX behavior).
   - Cover edge cases (e.g., empty lists, loading states, validation errors, etc...).

### Acceptance Criteria

A change is considered complete only when:
- Backend tests pass (if applicable)
- Browser verification confirms correct UI behavior

## Django Admin & Unfold Implementation

### Widget Selection for Dropdowns
When working with Django Admin and `django-unfold`, prioritize user experience for selection fields:

1.  **Use `autocomplete_fields`** for `ForeignKey` and `ManyToManyField` relationships when:
    - The related model has a large dataset (performance).
    - You need to search/filter the related objects efficiently.
    - *Requirement:* The related model's `ModelAdmin` must have `search_fields` defined.

2.  **Use `UnfoldAdminSelect2Widget`** (from `unfold.widgets`) for:
    - Standard `forms.ChoiceField` (enums, text choices).
    - Smaller `ForeignKey` lookups where `autocomplete_fields` is overkill but a searchable input is preferred over a native `<select>`.
    - Custom forms where you want consistent styling with the admin theme.

**Example:**
```python
from unfold.widgets import UnfoldAdminSelect2Widget

class MyForm(forms.ModelForm):
    class Meta:
        widgets = {
            "category": UnfoldAdminSelect2Widget,
        }
```
