"""Settings exclusively for the local, loopback-only Docker environment."""

import os

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
SECRET_KEY = os.environ.get("KIWI_SECRET_KEY", "local-image-build-only-not-for-runtime")
CSRF_TRUSTED_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]
SECURE_SSL_REDIRECT = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
ANONYMOUS_ANALYTICS = False
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
LANGUAGE_CODE = "ru"
KIWI_SHOW_ADS = False
