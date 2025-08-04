from settings import settings

# Database settings with custom schema for django-celery-beat
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": settings.ADA_DB_NAME,
        "USER": settings.ADA_DB_USER,
        "PASSWORD": settings.ADA_DB_PASSWORD,
        "HOST": settings.ADA_DB_HOST,
        "PORT": settings.ADA_DB_PORT,
        "OPTIONS": {"options": "-c search_path=django_beat_cron_scheduler,public"},
    }
}

# Standard django-celery-beat setup
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django_celery_beat",  # Standard django-celery-beat
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

# Middleware (standard)
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
    # Suppress model warnings
    "loggers": {
        "django.db.models": {
            "handlers": ["console"],
            "level": "ERROR",  # Only show errors, not warnings
        },
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
