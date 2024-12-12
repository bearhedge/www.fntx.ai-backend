from rest_framework import serializers

from ibkr.models import OnBoardingProcess


class OnboardingSerailizer(serializers.ModelSerializer):

    class Meta:
        model = OnBoardingProcess
        exclude = ('periodic_task',)
        depth = 1
