"""
Minimal Django settings for django-celery-beat compatibility.
This is used only by the Celery Beat scheduler.
"""

import os
from settings import settings

# Django settings configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': settings.ADA_DB_NAME,
        'USER': settings.ADA_DB_USER,
        'PASSWORD': settings.ADA_DB_PASSWORD,
        'HOST': settings.ADA_DB_HOST,
        'PORT': settings.ADA_DB_PORT,
    }
}

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django_celery_beat',
]

# Timezone settings
USE_TZ = True
TIME_ZONE = 'UTC'
USE_DEPRECATED_PYTZ = False

# Secret key (required by Django)
SECRET_KEY = 'django-celery-beat-minimal-config'

# Debug settings
DEBUG = False

# Database settings
DATABASE_OPTIONS = {}

# Middleware (minimal required)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]

# Cache settings (using database as cache)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_cache',
    }
}

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# Additional required settings
# ROOT_URLCONF = 'ada_backend.django_settings'  # Removed - not needed for django-celery-beat
# WSGI_APPLICATION = 'ada_backend.django_settings.application'  # Removed - not needed for django-celery-beat

# Application definition (minimal)
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Dummy application for WSGI
def application(environ, start_response):
    """Dummy WSGI application for django-celery-beat compatibility."""
    status = '200 OK'
    response_headers = [('Content-type', 'text/plain')]
    start_response(status, response_headers)
    return [b'Django-celery-beat compatibility layer'] 