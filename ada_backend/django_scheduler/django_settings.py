from settings import settings

# Override database settings to use the scheduled_workflows schema
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": settings.ADA_DB_NAME,
        "USER": settings.ADA_DB_USER,
        "PASSWORD": settings.ADA_DB_PASSWORD,
        "HOST": settings.ADA_DB_HOST,
        "PORT": settings.ADA_DB_PORT,
        "OPTIONS": {"options": "-c search_path=scheduled_workflows,public"},
    }
}

# Add our custom app to INSTALLED_APPS
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django_celery_beat",
    "ada_backend.django_scheduler",  # Our custom app with management commands
]

# Timezone settings
USE_TZ = True
TIME_ZONE = "UTC"
USE_DEPRECATED_PYTZ = False

# Secret key (required by Django)
SECRET_KEY = "django-celery-beat-minimal-config"

# Debug settings
DEBUG = False

# Database settings
DATABASE_OPTIONS = {}

# Middleware (minimal required)
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

# Cache settings (using database as cache)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# Templates configuration
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


class SchemaRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label == "django_celery_beat":
            return "default"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == "django_celery_beat":
            return "default"
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == "django_celery_beat":
            return db == "default"
        return None


DATABASE_ROUTERS = ["ada_backend.django_scheduler.django_settings.SchemaRouter"]

# Force table creation in schema by setting table prefix
TABLE_PREFIX = "scheduled_workflows."
