from django.contrib import admin

from ibkr.models import OnBoardingProcess, SystemData, TimerData

admin.site.register(OnBoardingProcess)
admin.site.register(SystemData)
admin.site.register(TimerData)