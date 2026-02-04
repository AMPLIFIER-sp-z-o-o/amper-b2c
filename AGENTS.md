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
- **New forms/modules**: Ensure draft preview is supported for new (unsaved) records; templates should receive model-specific context keys (e.g., `page`, `section`, `banner`) so previews render correctly.
- **Existing records**: Ensure draft preview applies to saved objects too (not just new records), so edited content renders on the live detail templates.
- **Inline lists in preview**: When draft changes affect inline items, avoid filtering by `is_active` before applying drafts. Apply drafts first, then filter and set `_draft_inline_applied` on remaining items so `apply_drafts_to_context` does not rebuild and reintroduce filtered items.

## Dev Workflows

| Task                | Command                                                                                                                                                                                                                                                                                                                                         |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bootstrap project   | `make init`                                                                                                                                                                                                                                                                                                                                     |
| Run dev servers     | `make dev` (Django + Vite) - **ONLY use this command to start the server. If the server is already running, do NOT start it again. Do not use manage.py runserver. During browser tests, NEVER start the server automatically unless it is found to be not running AFTER the tests have already begun - only then use `make dev` to start it.** |
| Django commands     | `uv run manage.py <cmd>` or `make manage ARGS='...'`                                                                                                                                                                                                                                                                                            |
| Run tests           | `make test` or `make test ARGS='apps.web.tests...'`                                                                                                                                                                                                                                                                                             |
| Format/lint         | `make ruff` (Ruff formatter + linter)                                                                                                                                                                                                                                                                                                           |
| Reset database      | `make reset-db` (drop + recreate + migrate)                                                                                                                                                                                                                                                                                                     |
| Update translations | `make translations`                                                                                                                                                                                                                                                                                                                             |
| Celery worker       | `make celery`                                                                                                                                                                                                                                                                                                                                   |

**Superuser credentials**: `admin@example.com` / `admin` (always use these credentials during testing)

## Environment & Integrations

- **Config**: `.env` via django-environ; defaults: Postgres port 7432, Redis port 7379.
- **Docker services**: `docker-compose.yml` runs Postgres + Redis containers.
- **Celery**: Redis broker; tasks auto-discovered; schedules in `SCHEDULED_TASKS` dict.
- **Media storage**: Configurable local/S3 via `MediaStorageSettings` model – storage cache clears on save.
- **Auth**: Custom `CustomUser` model; allauth adapters in [apps/users/adapter.py](../apps/users/adapter.py).

## Media Storage & Seed Data

### Storage Modes

This project supports **two storage backends** configured via `MediaStorageSettings` in Django Admin:

1. **S3 Storage** - files stored in AWS S3 bucket
2. **Local Storage** - files stored in `media/` folder on the server

### Git Rules for Media Files

**NEVER commit media files to the repository** - the `media/` folder is in `.gitignore`.

- When using **S3**: `media/` folder stays empty locally
- When using **Local Storage**: files are saved to `media/` but are NOT committed to git
- Each developer/environment manages their own media files

### Seed Data Architecture

`seed.py` contains **only database references** (paths like `product-images/xxx.jpg`), NOT actual files:

```python
# seed.py - only stores path references, not files
{"id": 37, "product_id": 50, "image": "product-images/energizer-max-aaa-4-pack.jpg", ...}
```

**Important:** The `_upload_if_missing()` function checks if files exist but does NOT include source files in the repo. Media files must be:

- Pre-uploaded to S3 (for S3 storage mode)
- OR manually placed in `media/` folder (for local storage mode)

### Storage Structure

```
# For S3 storage (bucket configured in MediaStorageSettings):
s3://<your-bucket>/
└── media/                    # MEDIA_URL prefix
    ├── product-images/       # Product photos
    ├── banners/              # Hero/content banners
    └── section_banners/      # Homepage section banners

# For Local storage:
media/                        # Local folder (gitignored)
├── product-images/
├── banners/
└── section_banners/
```

### Adding New Seed Images

1. Upload image to storage:
   - **S3**: Upload to `media/product-images/your-image.jpg` in your bucket
   - **Local**: Place file at `media/product-images/your-image.jpg`
2. Add database reference in `seed.py` PRODUCT_IMAGES_DATA:
   ```python
   {"id": X, "product_id": Y, "image": "product-images/your-image.jpg", ...}
   ```
3. Run `make reset-db-seed` - creates DB records pointing to files

### Troubleshooting Images

If images show wrong content after `make reset-db-seed`:

- The file in storage contains wrong data
- Seed only creates DB references - it doesn't manage file contents
- Fix by replacing the file directly in S3 or local `media/` folder

## Context Processors

Global template context provided by [apps/web/context_processors.py](../apps/web/context_processors.py):

- `project_meta` – SEO metadata from SiteSettings
- `top_bar`, `footer`, `bottom_bar` – site chrome configuration
- `site_currency` – for price display formatting

## Code Conventions

- **Language**: All code (variables, classes, etc.) and UI strings MUST be in **English**.
- **Translations**: UI strings must be translatable. Use `{% translate "..." %}` in templates and `_("...")` in Python code.
- Models: Extend `BaseModel`, use `_("...")` for translatable strings, define `__str__` and `get_absolute_url()`.
- Admin: Use Unfold components, readonly computed fields with `@admin.display(description=_(...))`.
- Views: Add to app's `urls.py`, use `reverse("app:view_name")` for URL generation.
- Templates: Extend `web/base.html`, use Flowbite components, include HTMX attributes for interactivity.

## UI Components & Styling

### Swiper/Slider Components (HTMX-Compatible Pattern)

This project uses [Swiper.js](https://swiperjs.com/) for carousels and sliders. To ensure sliders work correctly with **HTMX partial page updates**, follow these rules:

#### Architecture

1. **Swiper assets are loaded globally** in [templates/web/base.html](templates/web/base.html) — do NOT load Swiper CSS/JS in component templates.

2. **Initialization functions live in [assets/js/site.js](assets/js/site.js)** — NOT as inline `<script>` tags in templates. Inline scripts don't execute after HTMX swaps.

3. **Use data attributes** to pass template variables to JS:

   ```html
   <div
     class="swiper my-slider"
     data-category-id="{{ category.id }}"
     data-item-count="{{ items|length }}"
   ></div>
   ```

4. **Register HTMX afterSwap handlers** in site.js to reinitialize sliders after partial updates:
   ```javascript
   document.addEventListener("htmx:afterSwap", (event) => {
     if (event.target.id === "products-container") {
       initMySlider();
     }
   });
   ```

#### Available Slider Initializers

| Function                          | Selector                       | Description                               |
| --------------------------------- | ------------------------------ | ----------------------------------------- |
| `initCategoryRecommendedSlider()` | `.category-recommended-swiper` | Product recommendations on category pages |
| `initCategoryBannerSlider()`      | `.category-banner-swiper`      | Category page banner carousels            |

#### Adding a New Slider Component

1. **Template**: Create markup with Swiper classes and data-attributes (no inline scripts)
2. **site.js**: Add initialization function that reads data-attributes
3. **site.js**: Call function in `DOMContentLoaded` handler
4. **site.js**: Add `htmx:afterSwap` handler if the slider appears in HTMX-swapped content
5. **Export**: Add `window.myInitFunction = myInitFunction;` for debugging

#### ❌ Anti-Patterns (NEVER do this)

```html
<!-- DON'T: Load Swiper in component templates -->
<link rel="stylesheet" href="...swiper-bundle.min.css" />
<script src="...swiper-bundle.min.js"></script>

<!-- DON'T: Use inline scripts with template variables -->
<script>
  const count = {{ items|length }};  // Won't execute after HTMX swap!
  new Swiper('.my-slider', { loop: count > 1 });
</script>
```

#### ✅ Correct Pattern

```html
<!-- Template: Only markup + data attributes -->
<div class="swiper my-slider" data-item-count="{{ items|length }}">
  <div class="swiper-wrapper">...</div>
</div>
{# Initialization handled by site.js initMySlider() #}
```

```javascript
// site.js: Read data attributes, handle HTMX
function initMySlider() {
  document.querySelectorAll(".my-slider").forEach((el) => {
    if (el.swiper) return; // Already initialized
    const count = parseInt(el.dataset.itemCount, 10) || 0;
    new Swiper(el, { loop: count > 1 });
  });
}
window.initMySlider = initMySlider;
document.addEventListener("htmx:afterSwap", initMySlider);
```

### Hover Background Standards

All interactive elements (buttons, links, clickable icons) with hover backgrounds MUST use the **standardized hover style** for consistency across the application. This includes small utility icons like password toggles or search clear buttons.

**Standard hover classes (for elements on white/gray-50 backgrounds):**

```html
hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors
```

**For elements that already have a gray-200/gray-700 background:**

```html
hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors
```

**CSS utility classes** are available in [assets/css/site.css](assets/css/site.css):

- `.hover-bg` – Standard hover background with transitions
- `.hover-bg-active` – For elements with existing gray backgrounds

**NEVER use these combinations:**

- ❌ `dark:hover:bg-gray-600` – inconsistent with the rest of the app (use gray-700)
- ❌ `dark:hover:bg-gray-800` – too dark for interactive elements
- ❌ `hover:bg-gray-50` – too subtle, use gray-200
- ❌ `hover:bg-gray-100` – too subtle, use gray-200

**Exception:** Overlay UI elements (e.g., slider navigation buttons on images) may use different hover patterns like `hover:bg-white dark:hover:bg-gray-800` for visual contrast.

### Price Formatting

Always use **Polish locale (pl-PL)** for price formatting to display values correctly as "6,99 zł" instead of "PLN 6.99":

```javascript
// Correct format
new Intl.NumberFormat("pl-PL", { style: "currency", currency: "PLN" }).format(
  price,
);
// Result: "6,99 zł"

// WRONG - do NOT use
new Intl.NumberFormat("en-US", { style: "currency", currency: "PLN" }).format(
  price,
);
// Result: "PLN 6.99"
```

In templates, use the `site_currency` context variable for dynamic currency support.

### Input & Control Styling (Grayscale Standard)

To maintain a clean, modern aesthetic, interactive form elements and controls (inputs, checkboxes, pagination, sorting) MUST follow the **grayscale "elevated" style** instead of using default primary (blue) borders or focus outlines:

**1. Default State (Resting):**

- Use `bg-gray-100` background and `border-none`.
- For checkboxes/radios: `border-gray-300` or `dark:border-gray-600`.

**2. Focus/Active State (Elevated):**

- Background: `bg-white` (or `dark:bg-gray-700`).
- Border/Ring: `ring-0` or `border-none` (hide the default primary ring).
- Elevation: Apply a specific shadow for focus: `shadow-[0_4px_8px_0_rgba(0,0,0,0.16),0_0_2px_1px_rgba(0,0,0,0.08)]`.
- For Dark Mode: `dark:focus:shadow-[0_4px_8px_0_rgba(0,0,0/0.5),0_0_2px_1px_rgba(0,0,0/0.3)]`.

**3. Selection Indicators & Key Buttons:**

- **Primary Background Background Rule**: Key action buttons (like Search in header or "Add to Cart") and active selection indicators (like checked checkboxes in sidebars) MUST use the **primary brand color** (`bg-primary-600`) to increase visibility and brand consistency.
- Selected items in sorting or navigation (text-only) should be indicated by **font weight** (`font-bold` or `font-semibold`) and grayscale contrast (e.g., `text-gray-900`) rather than primary colors.
- Pagination: The active page should use the "Elevated" focus style (`bg-white` + shadow) while other pages stay `bg-gray-100`.

**Implementation Example (Input):**

```html
<input
  type="text"
  class="bg-gray-100 border-none focus:bg-white focus:ring-0 focus:shadow-[0_4px_8px_0_rgba(0,0,0,0.16),0_0_2px_1px_rgba(0,0,0,0.08)] transition-all ..."
/>
```

### Custom CSS Compatibility

Every new component or page section MUST be designed to support the **Custom CSS** functionality (managed in Site Settings). To enable granular styling via the admin:

- **Unique IDs**: Use a unique ID for the main container of each component, typically incorporating the database ID (e.g., `id="product-section-{{ section.id }}"`).
- **Semantic Classes**: Add descriptive, component-specific classes (e.g., `class="homepage-section section-product-list"`).
- **Predictable Selectors**: Ensure that all sub-elements can be easily targeted via CSS nesting starting from the component's unique ID or class.

Example pattern from `homepage_product_section.html`:

```html
<section
  id="product-section-{{ section.id }}"
  class="homepage-section section-product-list ..."
>
  <!-- Component content -->
</section>
```

## Change Validation & Testing

### Bug-First Development Workflow

When a bug is reported, **do not start by trying to fix it**. Instead:

1. **Write a test first** that reproduces the bug
2. Verify the test fails (proving the bug exists)
3. Have subagents attempt to fix the bug
4. Prove the fix with a passing test

This ensures bugs are properly documented and prevents regressions.

### When tests ARE required

Tests should be created for changes that:

- Modify **business logic** (e.g., calculations, validations, workflows)
- Change **behavior of existing functions** or API endpoints
- Add **new endpoints** or views
- Modify **data models** or relationships between them
- Introduce **edge case handling** or error handling

### When tests are NOT required

**Backend tests** can be skipped for purely cosmetic/configuration changes, however **browser verification is still mandatory** for any changes with visual impact:

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
  - All new media uploaded during verification/tests MUST be uploaded to AWS S3.
  - When adding new products for testing purposes, **reuse existing images** from the media storage instead of uploading new ones.

### Testing Tools

1. **Backend tests** (when required):
   - Use **pytest** + **pytest-django**.
   - Use `@pytest.mark.django_db` for functional tests or classes that don't inherit from `TestCase` and need database access.
   - Include positive and negative test scenarios.
   - Run via `make test`.

2. **Browser tests** (always required for **ALL** UI and visual changes):
   - **Environment**: Do NOT start the dev server (`make dev`) proactively. Only start it if the server is found to be not running AFTER startingbrowser verification.
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
    - _Requirement:_ The related model's `ModelAdmin` must have `search_fields` defined.

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
