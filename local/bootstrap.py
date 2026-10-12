"""Initialize a new local database without resetting existing users or data."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import django

django.setup()

from django.contrib.auth import get_user_model
from django.core.management import call_command

call_command("migrate", interactive=False)
call_command("set_domain", "127.0.0.1:8000")
call_command("refresh_permissions", interactive=False)

User = get_user_model()
username = os.environ["KIWI_ADMIN_USERNAME"]
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username=username,
        email=os.environ["KIWI_ADMIN_EMAIL"],
        password=os.environ["KIWI_ADMIN_PASSWORD"],
    )
    print(f"Created local administrator: {username}", flush=True)

os.execv(
    sys.executable,
    [sys.executable, "manage.py", "runserver", "0.0.0.0:8000", "--noreload"],
)
