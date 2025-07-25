from ada_backend.django_settings import django_settings
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
USE_TZ = django_settings.USE_TZ
TIME_ZONE = django_settings.TIME_ZONE
USE_DEPRECATED_PYTZ = django_settings.USE_DEPRECATED_PYTZ

# Secret key (required by Django)
SECRET_KEY = django_settings.SECRET_KEY

# Debug settings
DEBUG = django_settings.DEBUG

# Database settings
DATABASE_OPTIONS = django_settings.DATABASE_OPTIONS

# Middleware (minimal required)
MIDDLEWARE = django_settings.MIDDLEWARE

# Cache settings (using database as cache)
CACHES = django_settings.CACHES

# Logging configuration
LOGGING = django_settings.LOGGING

# Templates configuration
TEMPLATES = django_settings.TEMPLATES


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


DATABASE_ROUTERS = ["ada_backend.django_scheduler.settings.SchemaRouter"]

# Force table creation in schema by setting table prefix
TABLE_PREFIX = "scheduled_workflows."
