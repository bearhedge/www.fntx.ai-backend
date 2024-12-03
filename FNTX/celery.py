from __future__ import absolute_import, unicode_literals

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FNTX.settings")

app = Celery("FNTX")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

# Updated configuration for Celery 6.0 and above
app.conf.broker_connection_retry_on_startup = True
