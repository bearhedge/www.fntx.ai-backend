from rest_framework import serializers

from ibkr.models import OnBoardingProcess


class OnboardingSerailizer(serializers.ModelSerializer):

    class Meta:
        model = OnBoardingProcess
        fields = "__all__"
        depth = 1
