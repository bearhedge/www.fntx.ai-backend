from __future__ import absolute_import, unicode_literals

from .celery import app as celery_app

_all_ = ("celery_app",)