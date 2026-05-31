import os

from django.apps import AppConfig


class ApponeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'appone'

    def ready(self):
        if os.getenv("DISABLE_SCHEDULER") == "1":
            return
        from djangoProject.tools.TimeTask import ttime
        ttime.initscheduler()

