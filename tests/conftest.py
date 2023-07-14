import django
import os
import pytest
from django.test import utils

from django_scopes import scopes_disabled

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")


django.setup()

utils.setup_databases = scopes_disabled()(utils.setup_databases)


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    pass
