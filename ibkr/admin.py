from django.contrib import admin

from ibkr.models import OnBoardingProcess, SystemData, TimerData, Strikes

admin.site.register(OnBoardingProcess)
admin.site.register(SystemData)
admin.site.register(TimerData)
admin.site.register(Strikes)