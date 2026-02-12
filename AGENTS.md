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
- **Toast emphasis**: For toast/notification text that includes product names, only the product name should be emphasized (wrap the product name with `<strong>`). Do not bold action words like “Added” or “Removed”. Use safe HTML (e.g., `format_html`) so product names are escaped.
- Models: Extend `BaseModel`, use `_("...")` for translatable strings, define `__str__` and `get_absolute_url()`.
- Admin: Use Unfold components, readonly computed fields with `@admin.display(description=_(...))`.
- Views: Add to app's `urls.py`, use `reverse("app:view_name")` for URL generation.
- Templates: Extend `web/base.html`, use Flowbite components, include HTMX attributes for interactivity.

## DRY Principle & Component Reuse

This project strictly follows the **DRY (Don't Repeat Yourself)** principle. Any UI element, logic, or component that is used in more than one place MUST be extracted into a reusable unit:

1. **UI Components**: Recurring HTML patterns (buttons, inputs, cards, specialized widgets) MUST be extracted into Django template includes (typically in `templates/web/components/` or app-specific `includes/` folders).
2. **Logic & Utils**: Helper functions used across multiple views or models MUST be placed in `apps/utils/` or the relevant app's `helpers.py`.
3. **Styles**: Repeated Tailwind patterns should be extracted into CSS utility classes in `assets/css/site.css` (e.g., `.btn-press`, `.hover-bg`).
4. **JavaScript**: Reusable frontend logic MUST be defined in `assets/js/site.js` as global functions or modularized, avoiding inline `<script>` tags.

When implementing a feature, always check if a similar element already exists. If you find yourself copying more than 5-10 lines of HTML/JS, **stop and refactor it into a shared component**.

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

### Text Hierarchy & Subtitle Styling

This project uses a **two-tier text hierarchy** for secondary text. This is a strict rule to ensure proper readability and visual weight across the entire application.

#### Rule 1: Subtitle Text (`.text-subtitle`)

**Purpose**: For descriptive text that provides immediate context for a heading or title. This text must have high readability and good contrast.

- **Style**: `text-sm font-medium text-gray-600 dark:text-gray-300`
- **When to use**: Page descriptions directly under titles, summary info (e.g., "10 products · 200,00 zł total"), category descriptions.
- **Markup**: `<p class="text-subtitle mt-1">Manage your lists</p>`

#### Rule 2: Muted Text (`.text-muted`)

**Purpose**: For supplemental or helper information that is less critical for the user's primary flow.

- **Style**: `text-sm text-gray-500 dark:text-gray-400`
- **When to use**: Pagination info ("1-10 of 50"), empty state messages, form field hints, footer copyright, timestamps.
- **Markup**: `<span class="text-muted">Page 1 of 5</span>`

### Default Subtitle Style

All secondary/descriptive text under main headings (like "Start your shopping in seconds" on login or "Manage your lists" on favourites) MUST use the `.text-subtitle` utility class. This ensures a consistent look across the app with:

- **Font**: `text-sm font-medium`
- **Color**: `text-gray-600 dark:text-gray-300`

#### ❌ Anti-Patterns

- **DON'T** use `.text-muted` (gray-500) for main page subtitles; it lacks the visual weight required for good hierarchy.
- **DON'T** use manual Tailwind color classes (`text-gray-400`, etc.) for these elements—always use the semantic utility classes.

#### ✅ Example Hierarchy

```html
<h1 class="text-2xl font-bold">Favourites</h1>
<p class="text-subtitle mt-1">Manage your shopping lists and saved products</p>

<!-- Inside a list -->
<div class="mt-4">
  <h2 class="text-lg font-semibold">Summer Collection</h2>
  <span class="text-subtitle">12 products · 450,00 zł</span>
</div>
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

**Enforcement:** When adding hover backgrounds, prefer `.hover-bg`/`.hover-bg-active`; if you must use inline Tailwind classes, use `hover:bg-gray-200` (never `hover:bg-gray-100`).

**NEVER use these combinations:**

- ❌ `dark:hover:bg-gray-600` – inconsistent with the rest of the app (use gray-700)
- ❌ `dark:hover:bg-gray-800` – too dark for interactive elements
- ❌ `hover:bg-gray-50` – too subtle, use gray-200
- ❌ `hover:bg-gray-100` – too subtle, use gray-200

**Exception:** Overlay UI elements (e.g., slider navigation buttons on images) may use different hover patterns like `hover:bg-white dark:hover:bg-gray-800` for visual contrast.

### Button Pressed (Active) States

All interactive buttons that provide an action feedback (share, edit, settings-type buttons) MUST include a visible pressed/active state. This gives users tactile feedback that their click was registered.

**CSS utility class** available in [assets/css/site.css](assets/css/site.css):

- `.btn-press` – Applies `active:bg-gray-300 dark:active:bg-gray-600` with smooth transitions.

**Usage:**

```html
<button class="btn-press bg-gray-100 hover:bg-gray-200 ...">Share list</button>
```

**When to use:** Secondary/tertiary action buttons (share, edit, sort toggles). Primary CTA buttons (e.g., "Add to cart") already use `active:scale-95` for press feedback and do NOT need `.btn-press`.

### Disabled Button Hover Standards

Disabled buttons with `cursor-not-allowed` MUST NOT change their background or text color on hover. This is enforced globally via CSS in [assets/css/site.css](assets/css/site.css).

**For Tailwind-only buttons**, add these overrides alongside `disabled:opacity-40 disabled:cursor-not-allowed`:

```html
disabled:hover:bg-transparent disabled:hover:text-gray-500
dark:disabled:hover:text-gray-400 dark:disabled:hover:bg-transparent
```

**Example:**

```html
<button
  disabled
  class="text-gray-500 hover:text-red-600 hover:bg-gray-200
  disabled:opacity-40 disabled:cursor-not-allowed
  disabled:hover:bg-transparent disabled:hover:text-gray-500"
>
  Remove
</button>
```

### Async Button Loading States (Preventing Double-Clicks)

Every button that triggers an asynchronous operation (fetch, POST, AJAX) **MUST** show a loading state while the request is in progress. This prevents users from clicking multiple times and creating duplicate requests or bugs.

**Architecture:**

1. **CSS classes** are defined in [assets/css/site.css](assets/css/site.css): `.btn-loading`, `.btn-spinner`
2. **JS helpers** are defined in [assets/js/site.js](assets/js/site.js): `window.btnLoading(btn)`, `window.btnReset(btn)`
3. **cart.js** uses these helpers via event delegation for all `.add-to-cart-btn` and `.remove-cart-line` buttons

**How it works:**

- `btnLoading(btn)` — Adds `.btn-loading` class (dims button, disables pointer-events), hides children with `visibility: hidden`, and inserts an absolutely-positioned spinner overlay. The button remains the same size.
- `btnReset(btn)` — Removes `.btn-loading` class and spinner, restoring the button to normal.

**Rules:**

1. **Always guard against double-clicks**: Check `btn.classList.contains('btn-loading')` and `return` early if true.
2. **Call `btnLoading(btn)` before the fetch/POST**: The user sees immediate feedback.
3. **Call `btnReset(btn)` in the `finally` block** (or `.finally()` for promise chains): The button is restored whether the request succeeds or fails.
4. **For standard form submissions** (non-AJAX, server redirect): Call `btnLoading` in the `submit` event handler. No `btnReset` needed since the page navigates away.
5. **Do NOT use `cursor-not-allowed`** on loading buttons — the button should simply not respond to clicks (via `pointer-events: none`).
6. **Do NOT use `disabled` attribute** for loading state — use the CSS-based approach instead.

**Usage pattern (async/await):**

```javascript
btn.addEventListener('click', async (e) => {
  if (btn.classList.contains('btn-loading')) return;
  window.btnLoading(btn);
  try {
    const res = await fetch('/api/action/', { method: 'POST', ... });
    const data = await res.json();
    // handle response
  } catch (e) {
    // handle error
  } finally {
    window.btnReset(btn);
  }
});
```

**Usage pattern (event delegation with promises):**

```javascript
document.addEventListener('click', function(e) {
  const btn = e.target.closest('.my-action-btn');
  if (!btn || btn.classList.contains('btn-loading')) return;
  window.btnLoading(btn);

  fetch('/api/action/', { method: 'POST', ... })
    .then(res => res.json())
    .then(data => { /* handle */ })
    .catch(console.error)
    .finally(() => window.btnReset(btn));
});
```

**Which buttons require this:**

- All "Add to cart" buttons (`.add-to-cart-btn`) — handled by [static/js/cart.js](static/js/cart.js)
- All "Remove from cart" buttons (`.remove-cart-line`) — handled by cart.js
- All favourite/heart toggle buttons (`.favourite-btn`) — handled by [assets/js/site.js](assets/js/site.js)
- All "Create List", "Save Changes", "Delete List" modal submit buttons
- All bulk action buttons (bulk remove, copy to list, add to cart)
- Any new button that triggers a network request

### Form Submit Button Loading States (Standard Form Posts)

Every button that submits a standard (non-AJAX) form to the backend MUST show a loading state on submit. This prevents double-clicks and gives the user immediate feedback. Since the page navigates away on success, no `btnReset` is needed.

**Pattern:**

```html
<button
  id="my-submit-btn"
  type="submit"
  class="... inline-flex items-center justify-center gap-2 transition-all duration-200"
>
  <svg
    id="my-submit-spinner"
    class="hidden w-4 h-4 animate-spin"
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle
      class="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      stroke-width="4"
    ></circle>
    <path
      class="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    ></path>
  </svg>
  <span>Button Label</span>
</button>
<script>
  (function () {
    const form = document.querySelector('form[action="..."]');
    if (form) {
      form.addEventListener("submit", function () {
        const btn = document.getElementById("my-submit-btn");
        const spinner = document.getElementById("my-submit-spinner");
        if (btn && !btn.dataset.loading) {
          btn.dataset.loading = "true";
          btn.classList.add("opacity-60", "pointer-events-none");
          if (spinner) spinner.classList.remove("hidden");
        }
      });
    }
  })();
</script>
```

**Which form submit buttons require this:**

- Password reset request ("Send Reset Link")
- Password reset from key ("Change Password")
- Request login code ("Request Code")
- Confirm login code ("Confirm")
- Password change ("Change Password")
- Any new form submission button that posts to the backend

**Rules:**

1. Use `<button>` with `type="submit"` instead of `<input type="submit">` — buttons accept child elements (spinner SVG).
2. The spinner SVG is hidden by default (`class="hidden"`), shown on submit by removing `hidden`.
3. Use `opacity-60` + `pointer-events-none` to gray out button — never swap background colors.
4. Guard against double-submit by checking `btn.dataset.loading` before applying.
5. Wrap the label text in `<span>` so the spinner and text are properly flexed.

### Button Loading/Disabled Visual Style

When a button enters a loading or disabled state (e.g., after form submission), it MUST retain its original background color and only reduce opacity. **NEVER** swap the button's background to a gray color like `bg-gray-400` — this makes the button look too washed out and inconsistent.

**Correct pattern:**

```javascript
// Add opacity + disable pointer events — button keeps its original color
btn.classList.add("opacity-60", "pointer-events-none");
```

**NEVER do this:**

```javascript
// ❌ DON'T: Swap background to gray — too washed out
btn.classList.remove("bg-primary-600", "hover:bg-primary-700");
btn.classList.add("bg-gray-400", "pointer-events-none");
```

**Why:** The button should still look like itself (just dimmed) so the user understands the action is processing. Swapping to gray makes it look broken or permanently disabled rather than temporarily processing.

### Dropdown & Menu Text Weight

All dropdown menu items (context menus, sort dropdowns, action menus) MUST use `font-medium` (`text-sm font-medium`) for their text. Never use the default `font-normal` weight for dropdown items — thin text reduces readability and looks inconsistent with the rest of the UI.

### Typography Constraints

- **Font Size Restriction**: Never use `text-xs` for primary or interactive labels. `text-xs` is strictly reserved for secondary metadata or very small secondary hint text. For user identification (like email in dropdowns), use at least `text-sm` or ensure higher weight if `text-xs` must be used for layout reasons.
- **User Identification & Usernames**: All primary user identification labels (usernames, display names) MUST use `text-base font-medium` across the application. Never use `text-sm` for primary user identification.

**Example:**

```html
<button class="text-sm font-medium text-gray-700 dark:text-gray-300 ...">
  Share list
</button>
```

### Checkbox & Agreement Label Weight

Labels for checkboxes and agreement/consent text (e.g., "I agree to the Terms and Conditions") MUST use at least `font-normal` (400) weight. **NEVER** use `font-light` (300) for these labels — thin text reduces readability and makes important legal/consent text easy to overlook.

**Correct:**

```html
<label class="font-normal text-gray-600 dark:text-gray-300 cursor-pointer">
  I agree to the Terms and Conditions
</label>
```

**NEVER do this:**

```html
<!-- ❌ DON'T: font-light makes consent text too thin and hard to read -->
<label class="font-light text-gray-500 ...">...</label>
```

### Dropdown & Popover Open/Close Transitions

All dropdowns, context menus, and popovers that appear on click MUST use CSS transitions for opening and closing. Never toggle `hidden` class directly — this causes an instant, jarring appearance. Instead, use opacity + scale transitions.

**Pattern:** Use `opacity-0 scale-95 pointer-events-none` as the closed state and `opacity-100 scale-100` as the open state with `transition-all duration-150 ease-out`.

**Closed state (default):**

```html
<div
  class="... opacity-0 scale-95 pointer-events-none transition-all duration-150 ease-out"
></div>
```

**Open state (toggled via JS):**

```javascript
// Open
el.classList.remove("opacity-0", "scale-95", "pointer-events-none");
el.classList.add("opacity-100", "scale-100");

// Close
el.classList.add("opacity-0", "scale-95", "pointer-events-none");
el.classList.remove("opacity-100", "scale-100");
```

**NEVER do this:**

```javascript
// ❌ DON'T: Instant toggle without animation
el.classList.toggle("hidden");
```

### Navbar Dropdown Backdrop & Z-Index Layering

The navigation bar uses a **backdrop overlay** (`#nav-backdrop`) that dims the entire page when dropdowns (Cart, Account) or the categories drawer are open. To ensure all fixed/sticky elements on the page (e.g., sticky bottom bars) are properly dimmed:

#### Z-Index Hierarchy (MUST follow)

| Layer                        | Z-Index  | Purpose                                    |
| ---------------------------- | -------- | ------------------------------------------ |
| Sticky bottom bars           | `z-40`   | Fixed bars at page bottom (e.g., wishlist) |
| **Nav backdrop**             | `z-45`   | Dims everything below the navbar           |
| Nav / categories row         | `z-50`   | Main navigation bar                        |
| Category dropdowns container | `z-50`   | Dropdown menus from navbar                 |
| Categories drawer backdrop   | `z-[70]` | Drawer-specific backdrop (above nav)       |
| Categories drawer            | `z-80`   | Slide-out drawer panel                     |

**Rules:**

- Any **fixed or sticky bar** added to the page (e.g., bottom action bars, floating buttons) MUST use `z-40` or lower so the nav backdrop (`z-45`) covers it when dropdowns are open.
- **NEVER** set a fixed/sticky element to `z-45` or higher unless it is part of the navigation system itself.
- When adding new fixed/sticky UI elements, verify they are dimmed by the backdrop by testing with Cart or Account dropdown open.

#### Dropdown Transition Debouncing

When the user moves their mouse between adjacent navbar triggers (e.g., from "My Cart" to "Account"), the dropdown system uses a **debounced close** (`scheduleCloseAllDropdowns`) with a 100ms grace period. This prevents:

- Backdrop flickering on/off during transition
- Categories row shadow (`is-dimmed`) flashing
- Bottom bar dimming appearing and disappearing rapidly

**When modifying dropdown hover logic**, always use `scheduleCloseAllDropdowns()` instead of directly calling `closeAllDropdowns()` + `hideBackdrop()` in `mouseleave` handlers. Call `cancelScheduledClose()` in `openDropdown()` and in `mouseenter` handlers on dropdown elements to prevent premature closing.

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

### Toast Notifications

This project uses a unified toast notification system for both backend-driven messages (Django `messages` framework) and frontend-driven actions.

#### Architecture

1.  **Global Function**: `window.showToast(message, type)` is defined in `assets/js/site.js`.
2.  **Types**: Supported types are `'success'` (default) and `'error'`.
3.  **Django Integration**: [templates/web/components/messages.html](templates/web/components/messages.html) automatically converts Django backend messages into toasts. It waits for the page to be fully visible and for the JS to load before triggering them to ensure smooth animations.

#### Usage (Backend)

Use the standard Django messages framework:

```python
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

messages.success(request, _("Successfully performed action."))
messages.error(request, _("An error occurred."))
```

#### Usage (Frontend)

Call the global function:

```javascript
window.showToast("Item added to cart", "success");
window.showToast("Failed to update preferences", "error");
```

#### Best Practices

- **Timing**: Toasts are rendered with a small delay after page load for server-side messages to prevent them from flashing during the initial paint.
- **Translations**: Always ensure toast messages are translatable using `_()` in Python or `{% translate %}` / `{% blocktranslate %}` in templates.
- **Dismissal**: Toasts automatically dismiss after 5 seconds, but users can close them manually.
  In templates, use the `site_currency` context variable for dynamic currency support.

### Input & Control Styling (Grayscale Standard)

To maintain a clean, modern aesthetic, interactive form elements and controls (inputs, checkboxes, pagination, sorting) MUST follow the **grayscale "elevated" style** instead of using default primary (blue) borders or focus outlines:

**1. Default State (Resting):**

- Use `bg-gray-100` background and `border-none` for all text inputs across the application (auth pages, navbar search, filter bars, login code pages). This provides consistent visual weight and ensures the input boundary is visible on both white card and gray backgrounds.
- For checkboxes/radios: `border-gray-300` or `dark:border-gray-600`.
- **NEVER** use `bg-gray-50` for inputs — it is virtually invisible on white backgrounds and provides no visual affordance.
- **NEVER** use `bg-gray-200` for text inputs — it is too heavy and inconsistent with the rest of the app.

**2. Focus/Active State (Elevated):**

- Background: `bg-white` (or `dark:bg-gray-700`).
- Border/Ring: `ring-0` or `border-none` (hide the default primary ring).
- Elevation: Apply a specific shadow for focus: `shadow-[0_4px_8px_0_rgba(0,0,0,0.16),0_0_2px_1px_rgba(0,0,0,0.08)]`.
- For Dark Mode: `dark:focus:shadow-[0_4px_8px_0_rgba(0,0,0/0.5),0_0_2px_1px_rgba(0,0,0/0.3)]`.

**3. Selection Indicators & Key Buttons:**

- **Primary Background Background Rule**: Key action buttons (like Search in header or "Add to Cart") and active selection indicators (like checked checkboxes in sidebars) MUST use the **primary brand color** (`bg-primary-600`) to increase visibility and brand consistency.
- Selected items in sorting or navigation (text-only) should be indicated by **font weight** (`font-bold` or `font-semibold`) and grayscale contrast (e.g., `text-gray-900`) rather than primary colors.
- Pagination: The active page should use the "Elevated" focus style (`bg-white` + shadow) while other pages stay `bg-gray-100`.

**Implementation Example (Input on white card — auth pages):**

```html
<input
  type="text"
  class="bg-gray-100 border-none focus:bg-white focus:ring-0 focus:shadow-[0_4px_8px_0_rgba(0,0,0,0.16),0_0_2px_1px_rgba(0,0,0,0.08)] transition-all ..."
/>
```

**Implementation Example (Input on gray background — navbar/filters):**

```html
<input
  type="text"
  class="bg-gray-100 border-none focus:bg-white focus:ring-0 focus:shadow-[0_4px_8px_0_rgba(0,0,0,0.16),0_0_2px_1px_rgba(0,0,0,0.08)] transition-all ..."
/>
```

#### ❌ Anti-Patterns

```html
<!-- DON'T: bg-gray-50 is invisible on white backgrounds -->
<input class="bg-gray-50 border-none ..." />
<!-- DON'T: bg-gray-200 is too heavy -->
<input class="bg-gray-200 border-none ..." />
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

### Shared Product Card Components (MUST Reuse)

When displaying products in **any** view (category pages, favourites, search results, new features), you **MUST** reuse the existing shared card components via `{% include %}`. **NEVER** duplicate or copy-paste product card HTML into a new template. This is a **strict architectural rule** — every product tile in the application is a single shared component imported wherever needed. If you need to display a product in a new page or section, **always `{% include %}` one of the components below**. Do NOT create a new card template.

#### Available Card Components

| Component           | Path                                                         | Purpose                                              |
| ------------------- | ------------------------------------------------------------ | ---------------------------------------------------- |
| **List card**       | `templates/web/components/product_list_card.html`            | Horizontal card for list/row views                   |
| **Grid card**       | `templates/web/components/homepage_product_card.html`        | Vertical card for grid layouts                       |
| **Slider card**     | `templates/web/components/homepage_product_slider_card.html` | Card for Swiper slider carousels                     |
| **Tile attributes** | `templates/web/components/product_tile_attributes.html`      | Shared attribute pills (used inside card components) |

#### Where Each Component Is Currently Used

These are all **the same shared component** imported in multiple places — no duplication:

- **List card** (`product_list_card.html`):
  - Category page list view → `templates/web/product_list_partial.html`
  - Favourites page → `templates/favourites/partials/wishlist_items.html`
- **Grid card** (`homepage_product_card.html`):
  - Category page grid view → `templates/web/product_list_partial.html`
  - Homepage product sections → `templates/web/components/homepage_product_section.html`
  - Category recommended products → `templates/web/components/category_recommended_products.html`
- **Slider card** (`homepage_product_slider_card.html`):
  - Homepage slider sections → `templates/web/components/homepage_product_slider_section.html`

When adding a new page or feature that shows products, **pick from the table above and `{% include %}` it** — do not create any new card template.

#### Context Variables

All card components accept a `product` variable. Additional optional context:

- **`is_favourited`** (bool) – Pre-fills the heart/favourite icon as active. Used on the favourites page where all displayed products are already favourited.

#### Usage Examples

```django-html
{# Category page (list view) – standard usage #}
{% include "web/components/product_list_card.html" with product=product %}

{# Favourites page – pre-fill heart icon #}
{% include "web/components/product_list_card.html" with product=item.product is_favourited=True %}

{# Homepage grid #}
{% include "web/components/homepage_product_card.html" with product=product %}
```

#### Adding New Context Variables

If a new view needs slightly different card behavior (e.g., a "compare" button), **extend the existing component** with a new optional context variable instead of forking the template. Follow the `is_favourited` pattern:

1. Add conditional logic inside the shared component that checks for the variable
2. Default behavior when variable is absent must remain unchanged
3. Pass the variable via `{% include ... with my_var=value %}`

#### ❌ Anti-Pattern (NEVER do this)

```django-html
{# DON'T: Copy card HTML into your template #}
<div class="product-card ...">
  <img src="{{ product.primary_image }}">
  <h3>{{ product.name }}</h3>
  <!-- 80+ lines of duplicated card markup -->
</div>

{# DON'T: Create a new card template for a new page #}
{# e.g., templates/my_new_feature/product_card.html — WRONG #}
```

#### ✅ Correct Pattern

```django-html
{# DO: Always include the shared component #}
{% include "web/components/product_list_card.html" with product=product %}
```

### Shared Auth Page Components (MUST Reuse)

All **repeated UI components across authentication pages** (login, signup, password reset, login code, etc.) are defined as shared Django template includes in `templates/account/includes/`. When modifying or adding auth pages, you **MUST** reuse these shared components via `{% include %}`. **NEVER** duplicate auth component HTML/JS across multiple templates.

#### Available Auth Includes

| Component               | Path                                                  | Parameters                                      | Purpose                                        |
| ----------------------- | ----------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------- |
| **Auth card CSS**       | `templates/account/includes/auth_card_css.html`       | _(none)_                                        | Entrance animation keyframes for auth cards    |
| **Eye toggle**          | `templates/account/includes/eye_toggle.html`          | `input_id`, `toggle_id`, `eye_id`, `eye_off_id` | Password visibility toggle button + script     |
| **Password strength**   | `templates/account/includes/password_strength.html`   | `password_input_id`, optional `email_input_id`  | Strength meter bars + requirements + script    |
| **Password match**      | `templates/account/includes/password_match.html`      | `password1_id`, `password2_id`                  | Password confirmation match indicator + script |
| **Form submit loading** | `templates/account/includes/form_submit_loading.html` | `btn_id`, `spinner_id`                          | Button loading state on form submit            |

#### Usage Examples

```django-html
{# Auth card animation (in {% block page_head %}) #}
{% include "account/includes/auth_card_css.html" %}

{# Eye toggle inside <div class="relative"> wrapper #}
{% include "account/includes/eye_toggle.html" with input_id=form.password.id_for_label toggle_id="toggle-password" eye_id="eye-icon" eye_off_id="eye-off-icon" %}

{# Password strength meter (with email similarity check on signup) #}
{% include "account/includes/password_strength.html" with password_input_id=form.password1.id_for_label email_input_id=form.email.id_for_label %}

{# Password strength meter (without email check, e.g. password reset) #}
{% include "account/includes/password_strength.html" with password_input_id=form.password1.id_for_label %}

{# Password match validation #}
{% include "account/includes/password_match.html" with password1_id=form.password1.id_for_label password2_id=form.password2.id_for_label %}

{# Form submit loading state #}
{% include "account/includes/form_submit_loading.html" with btn_id="my-btn" spinner_id="my-spinner" %}
```

#### Rules

1. **One source of truth**: If you need to change how the eye toggle looks or how the strength meter calculates score, edit the include file — all pages update automatically.
2. **Extending behavior**: If a new auth page needs a variation of an existing component, add an **optional context variable** to the existing include (like `email_input_id` for the email similarity check). Do NOT fork the template.
3. **New auth components**: If a new reusable pattern emerges across auth pages, extract it into `templates/account/includes/` and update this table.

#### ❌ Anti-Pattern (NEVER do this)

```django-html
{# DON'T: Copy-paste eye toggle HTML/JS into a new template #}
<button type="button" id="toggle-password" class="absolute ...">
  <svg id="eye-icon" ...>...</svg>
  <svg id="eye-off-icon" class="hidden" ...>...</svg>
</button>
<script>
  document.getElementById('toggle-password').addEventListener('click', function() { ... });
</script>
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
