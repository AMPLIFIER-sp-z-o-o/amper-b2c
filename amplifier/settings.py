"""
Django settings for AMPLFIER sp. z o.o. project.

For more information on this file, see
https://docs.djangoproject.com/en/stable/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/stable/ref/settings/
"""

import os
import sys
from pathlib import Path

import environ
from corsheaders.defaults import default_headers
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy

# Build paths inside the project like this: BASE_DIR / "subdir".
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env"))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/stable/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY", default="django-insecure-EE3FQvzKcHSF5NZeUTZuvDi7pD2OJgeJordFzhs1")

# SECURITY WARNING: don"t run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=True)
ENABLE_DEBUG_TOOLBAR = env.bool("ENABLE_DEBUG_TOOLBAR", default=False) and "test" not in sys.argv

# Note: It is not recommended to set ALLOWED_HOSTS to "*" in production
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])


# Application definition

DJANGO_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.import_export",
    "unfold.contrib.simple_history",
    "import_export",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sitemaps",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.redirects",
    "django.forms",
]

PROJECT_METADATA = {
    "NAME": gettext_lazy("AMPLFIER sp. z o.o."),
    "URL": "http://localhost:8000",
    "DESCRIPTION": gettext_lazy("AMPER-B2C is a top-notch, next-gen  B2C e-commerce solution."),  # noqa: E501
    "IMAGE": None,
    "KEYWORDS": "e-commerce, amper-b2c",
}

# Put your third-party apps here
THIRD_PARTY_APPS = [
    "allauth",  # allauth account/registration management
    "allauth.account",
    "allauth.headless",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.facebook",
    "allauth.socialaccount.providers.twitter_oauth2",
    "channels",
    "django_htmx",
    "django_watchfiles",
    "django_vite",
    "django_ckeditor_5",
    "allauth.mfa",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "drf_spectacular",
    "rest_framework_api_key",
    "celery_progress",
    "hijack",  # "login as" functionality
    "hijack.contrib.admin",  # hijack buttons in the admin
    "health_check",
    "health_check.db",
    "health_check.contrib.celery",
    "health_check.contrib.redis",
    "django_celery_beat",
    "simple_history",
    "colorfield",
]

# Put your project-specific apps here
PROJECT_APPS = [
    "apps.users.apps.UserConfig",
    "apps.api.apps.APIConfig",
    "apps.web.apps.WebConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.media.apps.MediaConfig",
    "apps.homepage.apps.HomepageConfig",
    "apps.support.apps.SupportConfig",
    "apps.cart.apps.CartConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + PROJECT_APPS

UNFOLD = {
    "SITE_TITLE": "AMPER B2C Admin",
    "SITE_HEADER": "AMPER B2C",
    "STYLES": [
        # Custom admin styles are loaded via vite_asset in templates/admin/base.html
    ],
    "SCRIPTS": [
        "/static/js/admin_custom.js",
    ],
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": gettext_lazy("Catalog"),
                "icon": "store",
                "collapsible": True,
                "items": [
                    {
                        "title": gettext_lazy("Products"),
                        "link": reverse_lazy("admin:catalog_product_changelist"),
                    },
                    {
                        "title": gettext_lazy("Categories"),
                        "link": reverse_lazy("admin:catalog_category_changelist"),
                    },
                    {
                        "title": gettext_lazy("Attributes"),
                        "link": reverse_lazy("admin:catalog_attributedefinition_changelist"),
                    },
                ],
            },
            {
                "title": gettext_lazy("Homepage"),
                "icon": "home",
                "collapsible": True,
                "items": [
                    {
                        "title": gettext_lazy("Hero Banners"),
                        "link": reverse_lazy("admin:homepage_bannergroup_changelist"),
                    },
                    {
                        "title": gettext_lazy("Sections"),
                        "link": reverse_lazy("admin:homepage_homepagesection_changelist"),
                    },
                ],
            },
            {
                "title": gettext_lazy("Media Storage"),
                "icon": "perm_media",
                "collapsible": True,
                "items": [
                    {
                        "title": gettext_lazy("Media library"),
                        "link": reverse_lazy("admin:media_mediafile_changelist"),
                    },
                    {
                        "title": gettext_lazy("Storage settings"),
                        "link": reverse_lazy("admin:media_mediastoragesettings_changelist"),
                    },
                ],
            },
            {
                "title": gettext_lazy("Social accounts"),
                "icon": "share",
                "collapsible": True,
                "items": [
                    {
                        "title": gettext_lazy("Accounts"),
                        "link": reverse_lazy("admin:socialaccount_socialaccount_changelist"),
                    },
                    {
                        "title": gettext_lazy("Applications"),
                        "link": reverse_lazy("admin:socialaccount_socialapp_changelist"),
                    },
                ],
            },
            {
                "title": gettext_lazy("Users"),
                "icon": "people",
                "collapsible": True,
                "items": [
                    {
                        "title": gettext_lazy("Users"),
                        "link": reverse_lazy("admin:users_customuser_changelist"),
                    },
                    {
                        "title": gettext_lazy("Groups"),
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
            {
                "title": gettext_lazy("Web"),
                "icon": "web",
                "collapsible": True,
                "items": [
                    {
                        "title": gettext_lazy("Top bar"),
                        "link": reverse_lazy("admin:web_topbar_changelist"),
                    },
                    {
                        "title": gettext_lazy("Navigation bar"),
                        "link": reverse_lazy("admin:web_navbar_changelist"),
                    },
                    {
                        "title": gettext_lazy("Footer"),
                        "link": reverse_lazy("admin:web_footer_changelist"),
                    },
                    {
                        "title": gettext_lazy("Bottom bar"),
                        "link": reverse_lazy("admin:web_bottombar_changelist"),
                    },
                    {
                        "title": gettext_lazy("Site Settings"),
                        "link": reverse_lazy("admin:web_sitesettings_changelist"),
                    },
                    {
                        "title": gettext_lazy("Dynamic pages"),
                        "link": reverse_lazy("admin:web_dynamicpage_changelist"),
                    },
                    {
                        "title": gettext_lazy("Custom CSS"),
                        "link": reverse_lazy("admin:web_customcss_changelist"),
                    },
                ],
            },
        ],
    },
}

if DEBUG:
    # in debug mode, add daphne to the beginning of INSTALLED_APPS to enable async support
    INSTALLED_APPS.insert(0, "daphne")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.redirects.middleware.RedirectFallbackMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "apps.media.middleware.CurrentUserMiddleware",
    "apps.support.middleware.admin_draft_cleanup.AdminDraftCleanupMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.web.middleware.locale.UserLocaleMiddleware",
    "apps.web.middleware.locale.UserTimezoneMiddleware",
    "apps.web.middleware.draft_preview.DraftPreviewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "hijack.middleware.HijackUserMiddleware",
]

MESSAGE_STORAGE = "apps.support.message_storage.AdminScopedFallbackStorage"

if ENABLE_DEBUG_TOOLBAR:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INSTALLED_APPS.append("debug_toolbar")
    INTERNAL_IPS = ["127.0.0.1"]

if DEBUG:
    INSTALLED_APPS.append("django_browser_reload")
    MIDDLEWARE.append("django_browser_reload.middleware.BrowserReloadMiddleware")

ROOT_URLCONF = "amplifier.urls"

# used to disable the cache in dev, but turn it on in production.
# more here: https://nickjanetakis.com/blog/django-4-1-html-templates-are-cached-by-default-with-debug-true
_DEFAULT_LOADERS = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]

_CACHED_LOADERS = [("django.template.loaders.cached.Loader", _DEFAULT_LOADERS)]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.web.context_processors.project_meta",
                # this line can be removed if not using google analytics
                "apps.web.context_processors.google_analytics_id",
                "apps.web.context_processors.site_settings",
                "apps.web.context_processors.top_bar_section",
                "apps.web.context_processors.footer_context",
                "apps.web.context_processors.bottom_bar_context",
                "apps.web.context_processors.navigation_categories",
                "apps.support.context_processors.admin_extra_userlinks",
                "apps.support.context_processors.draft_preview",
            ],
            "loaders": _DEFAULT_LOADERS if DEBUG else _CACHED_LOADERS,
        },
    },
]

WSGI_APPLICATION = "amplifier.wsgi.application"

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# Database
# https://docs.djangoproject.com/en/stable/ref/settings/#databases

if "DATABASE_URL" in env:
    DATABASES = {"default": env.db()}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DJANGO_DATABASE_NAME", default="amplifier"),
            "USER": env("DJANGO_DATABASE_USER", default="postgres"),
            "PASSWORD": env("DJANGO_DATABASE_PASSWORD", default="***"),
            "HOST": env("DJANGO_DATABASE_HOST", default="localhost"),
            "PORT": env("DJANGO_DATABASE_PORT", default="7432"),
        }
    }

# Auth and Login

# Django recommends overriding the user model even if you don"t think you need to because it makes
# future changes much easier.
AUTH_USER_MODEL = "users.CustomUser"
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"

# Password validation
# https://docs.djangoproject.com/en/stable/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Allauth setup

ACCOUNT_ADAPTER = "apps.users.adapter.EmailAsUsernameAdapter"
HEADLESS_ADAPTER = "apps.users.adapter.CustomHeadlessAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]

ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False  # don't send "forgot password" emails to unknown accounts
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_UNIQUE_EMAIL = True
# This configures a honeypot field to prevent bots from signing up.
# The ID strikes a balance of "realistic" - to catch bots,
# and "not too common" - to not trip auto-complete in browsers.
# You can change the ID or remove it entirely to disable the honeypot.
ACCOUNT_SIGNUP_FORM_HONEYPOT_FIELD = "phone_number_x"
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_USER_DISPLAY = lambda user: user.get_display_name()  # noqa: E731

ACCOUNT_FORMS = {
    "signup": "apps.users.forms.TermsSignupForm",
}
SOCIALACCOUNT_FORMS = {
    "signup": "apps.users.forms.CustomSocialSignupForm",
}

FRONTEND_ADDRESS = env("FRONTEND_ADDRESS", default="http://localhost:5174")
USE_HEADLESS_URLS = env.bool("USE_HEADLESS_URLS", default=False)
if USE_HEADLESS_URLS:
    # These URLs will use the React front end instead of the Django views
    HEADLESS_FRONTEND_URLS = {
        "account_confirm_email": f"{FRONTEND_ADDRESS}/account/verify-email/{{key}}",
        "account_reset_password_from_key": f"{FRONTEND_ADDRESS}/account/password/reset/key/{{key}}",
        "account_signup": f"{FRONTEND_ADDRESS}/account/signup",
    }

# needed for cross-origin CSRF
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[FRONTEND_ADDRESS])
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN", default=None)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (*default_headers, "x-password-reset-key", "x-email-verification-key")
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[FRONTEND_ADDRESS])
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN", default=None)

# User signup configuration: change to "mandatory" to require users to confirm email before signing in.
# or "optional" to send confirmation emails but not require them
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="none")

AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",
    # `allauth` specific authentication methods, such as login by e-mail
    "allauth.account.auth_backends.AuthenticationBackend",
)

# enable social login
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    },
    "facebook": {
        "METHOD": "oauth2",
        "SCOPE": ["email", "public_profile"],
        "FIELDS": ["id", "email", "name", "first_name", "last_name"],
        "VERSION": "v18.0",
    },
    "twitter_oauth2": {
        "SCOPE": ["users.read"],
    },
}

# For turnstile captchas
TURNSTILE_KEY = env("TURNSTILE_KEY", default=None)
TURNSTILE_SECRET = env("TURNSTILE_SECRET", default=None)


# Internationalization
# https://docs.djangoproject.com/en/stable/topics/i18n/

LANGUAGE_CODE = "en-us"
LANGUAGE_COOKIE_NAME = "amplifier_language"
LANGUAGES = [
    ("en", gettext_lazy("English")),
    ("pl", gettext_lazy("Polish")),
]
LOCALE_PATHS = (BASE_DIR / "locale",)

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

STATIC_ROOT = BASE_DIR / "static_root"
STATIC_URL = env("STATIC_URL", default="/static/")

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # swap these to use manifest storage to bust cache when files change
        # note: this may break image references in sass/css files which is why it is not enabled by default
        # "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

USE_S3_MEDIA = env.bool("USE_S3_MEDIA", default=False)
if USE_S3_MEDIA:
    # Media file storage in S3
    # Using this will require configuration of the S3 bucket
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="amplifier-media")
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
    PUBLIC_MEDIA_LOCATION = "media"
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{PUBLIC_MEDIA_LOCATION}/"
    STORAGES["default"] = {
        "BACKEND": "apps.web.storage_backends.PublicMediaStorage",
    }

# Vite Integration
DJANGO_VITE = {
    "default": {
        "dev_mode": env.bool("DJANGO_VITE_DEV_MODE", default=DEBUG),
        "manifest_path": BASE_DIR / "static" / ".vite" / "manifest.json",
    }
}

# Default primary key field type
# https://docs.djangoproject.com/en/stable/ref/settings/#default-auto-field

# future versions of Django will use BigAutoField as the default, but it can result in unwanted library
# migration files being generated, so we stick with AutoField for now.
# change this to BigAutoField if you"re sure you want to use it and aren"t worried about migrations.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Removes deprecation warning for future compatibility.
# see https://adamj.eu/tech/2023/12/07/django-fix-urlfield-assume-scheme-warnings/ for details.
FORMS_URLFIELD_ASSUME_HTTPS = True

# Email setup

# default email used by your server
SERVER_EMAIL = env("SERVER_EMAIL", default="noreply@localhost:8000")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="tomek@dziemidowicz.cloud")

# The default value will print emails to the console, but you can change that here
# and in your environment.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

# Most production backends will require further customization. The below example uses Mailgun.
# ANYMAIL = {
#     "MAILGUN_API_KEY": env("MAILGUN_API_KEY", default=None),
#     "MAILGUN_SENDER_DOMAIN": env("MAILGUN_SENDER_DOMAIN", default=None),
# }

# use in production
# see https://github.com/anymail/django-anymail for more details/examples
# EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"

EMAIL_SUBJECT_PREFIX = "[AMPLFIER sp. z o.o.] "

# Django sites

SITE_ID = 1

# DRF config
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ("apps.api.permissions.IsAuthenticatedOrHasUserAPIKey",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
}


SPECTACULAR_SETTINGS = {
    "TITLE": "AMPLFIER sp. z o.o.",
    "DESCRIPTION": "AMPER is a top-notch, next-gen SFA/FFM/e-commerce solution.",  # noqa: E501
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {
        "displayOperationId": True,
    },
    "APPEND_COMPONENTS": {
        "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "Authorization"}}
    },
    "SECURITY": [
        {
            "ApiKeyAuth": [],
        }
    ],
}
# Redis, cache, and/or Celery setup
if "REDIS_URL" in env:
    REDIS_URL = env("REDIS_URL")
elif "REDIS_TLS_URL" in env:
    REDIS_URL = env("REDIS_TLS_URL")
else:
    REDIS_HOST = env("REDIS_HOST", default="localhost")
    REDIS_PORT = env("REDIS_PORT", default="7379")
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

if REDIS_URL.startswith("rediss"):
    REDIS_URL = f"{REDIS_URL}"

DUMMY_CACHE = {
    "BACKEND": "django.core.cache.backends.dummy.DummyCache",
}
REDIS_CACHE = {
    "BACKEND": "django.core.cache.backends.redis.RedisCache",
    "LOCATION": REDIS_URL,
}
CACHES = {
    "default": DUMMY_CACHE if DEBUG else REDIS_CACHE,
}

CELERY_BROKER_URL = CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Add tasks to this dict and run `python manage.py bootstrap_celery_tasks` to create them
SCHEDULED_TASKS = {
    # Example of a crontab schedule
    # from celery import schedules
    # "daily-4am-task": {
    #     "task": "some.task.path",
    #     "schedule": schedules.crontab(minute=0, hour=4),
    # },
}

# Channels / Daphne setup

ASGI_APPLICATION = "amplifier.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Health Checks
# A list of tokens that can be used to access the health check endpoint
HEALTH_CHECK_TOKENS = env.list("HEALTH_CHECK_TOKENS", default="")

# set this to True in production to have URLs generated with https instead of http
USE_HTTPS_IN_ABSOLUTE_URLS = env.bool("USE_HTTPS_IN_ABSOLUTE_URLS", default=False)

DRAFT_PREVIEW_TTL_MINUTES = env.int("DRAFT_PREVIEW_TTL_MINUTES", default=1440)

ADMINS = ["tomek@dziemidowicz.cloud"]

# Add your google analytics ID to the environment to connect to Google Analytics
GOOGLE_ANALYTICS_ID = env("GOOGLE_ANALYTICS_ID", default="")

# these daisyui themes are used to set the dark and light themes for the site
# they must be valid themes included in your tailwind.config.js file.
# more here: https://daisyui.com/docs/themes/
LIGHT_THEME = "light"
DARK_THEME = "dark"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": '[{asctime}] {levelname} "{name}" {message}',
            "style": "{",
            "datefmt": "%d/%b/%Y %H:%M:%S",  # match Django server time format
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
        },
        "amplifier": {
            "handlers": ["console"],
            "level": env("AMPLIFIER_LOG_LEVEL", default="INFO"),
        },
    },
}

# CKEditor 5 Configuration
CKEDITOR_5_CONFIGS = {
    "default": {
        "toolbar": [
            "heading",
            "|",
            "bold",
            "italic",
            "|",
            "link",
            "|",
            "bulletedList",
            "numberedList",
            "|",
            "blockQuote",
            "|",
            "undo",
            "redo",
        ],
    },
    "extends": {
        "toolbar": [
            "heading",
            "|",
            "bold",
            "italic",
            "link",
            "bulletedList",
            "|",
            "fontSize",
            "fontColor",
            "fontBackgroundColor",
            "|",
            "alignment",
            "numberedList",
            "|",
            "imageInsert",
            "insertTable",
            "mediaEmbed",
            "horizontalLine",
            "|",
            "sourceEditing",
            "underline",
        ],
        "image": {
            "toolbar": [
                "imageTextAlternative",
                "|",
                "imageStyle:inline",
                "imageStyle:wrapText",
                "imageStyle:breakText",
                "|",
                "resizeImage",
            ],
        },
        "table": {
            "contentToolbar": [
                "tableColumn",
                "tableRow",
                "mergeTableCells",
                "tableProperties",
                "tableCellProperties",
            ],
        },
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Paragraph", "class": "ck-heading_paragraph"},
                {"model": "heading1", "view": "h1", "title": "Heading 1", "class": "ck-heading_heading1"},
                {"model": "heading2", "view": "h2", "title": "Heading 2", "class": "ck-heading_heading2"},
                {"model": "heading3", "view": "h3", "title": "Heading 3", "class": "ck-heading_heading3"},
                {"model": "heading4", "view": "h4", "title": "Heading 4", "class": "ck-heading_heading4"},
            ],
        },
        "wordCount": {
            "displayWords": False,
            "displayCharacters": False,
        },
    },
}

CKEDITOR_5_FILE_STORAGE = "apps.media.storage.DynamicMediaStorage"
CKEDITOR_5_FILE_UPLOAD_PERMISSION = "authenticated"
CKEDITOR_5_UPLOAD_FILE_TYPES = ["jpeg", "jpg", "png", "gif", "webp", "svg"]
