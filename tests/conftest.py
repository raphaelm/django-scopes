import os
from django.test import utils

from django_scopes import scopes_disabled

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import django

django.setup()

utils.setup_databases = scopes_disabled()(utils.setup_databases)
