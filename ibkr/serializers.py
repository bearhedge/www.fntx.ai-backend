from rest_framework import serializers

from ibkr.models import OnBoardingProcess, SystemData, OrderData, TradingStatus ,Instrument


class OnboardingSerailizer(serializers.ModelSerializer):

    class Meta:
        model = OnBoardingProcess
        fields = "__all__"
        depth = 1

class SystemDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemData
        fields = '__all__'

class OrderDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderData
        fields = '__all__'

class TradingStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingStatus
        fields = '__all__'

class InstrumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instrument
        fields = '__all__'