"""Use Django's extractor directly: vinaigrette's command predates Django 6.

Run in the test container; arguments are passed through to makemessages.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from django.core.management.commands.makemessages import Command

Command.msgmerge_options = [*Command.msgmerge_options, "--no-fuzzy-matching"]
Command().run_from_argv(
    [
        "manage.py",
        "makemessages",
        "--ignore=node_modules",
        "--ignore=.git",
        "--ignore=.local-*",
        "--ignore=tests",
        "--ignore=migrations",
        *sys.argv[1:],
    ]
)
