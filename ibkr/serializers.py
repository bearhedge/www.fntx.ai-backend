import requests
from django.conf import settings
from rest_framework import serializers
from ibkr.utils import fetch_bounds_from_json
from ibkr.models import TimerData, OnBoardingProcess, SystemData, OrderData, TradingStatus ,Instrument
from core.views import IBKRBase
import re


class OnboardingSerailizer(serializers.ModelSerializer):
    class Meta:
        model = OnBoardingProcess
        exclude = ('periodic_task',)
        depth = 1

class SystemDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemData
        exclude = ('user', )


class SystemDataListSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemData
        exclude = ('user', )
        depth = 1


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


class TimerDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimerData
        fields = ['timer_value', 'start_time']

class TimerDataListSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimerData
        fields = '__all__'


class UpperLowerBoundSerializer(serializers.Serializer):
    time_frame = serializers.ChoiceField(choices=SystemData.TIME_FRAME_CHOICES)  # Validates against predefined choices
    time_steps = serializers.IntegerField()  # Positive integer for time steps
    conid = serializers.IntegerField()  # Integer representing contract ID

    def validate(self, data):
        time_frame_mapping = dict(SystemData.TIME_FRAME_CHOICES)
        time_frame = data.get('time_frame')
        time_steps = data.get('time_steps')
        if time_frame not in time_frame_mapping:
            raise serializers.ValidationError("Invalid time frame.")
        if time_steps <= 0:
            raise serializers.ValidationError("Time steps must be a positive integer.")
        time_unit = time_frame_mapping[time_frame]

        # Use regex to extract the numerical part and the unit part
        match = re.match(r"(\d+)(\D+)", time_unit)
        if not match:
            raise serializers.ValidationError("Invalid time unit format.")

        numerical_part = int(match.group(1))
        unit_part = match.group(2)

        data['period'] = f"{time_steps * numerical_part}{unit_part}"
        data['conid'] = f"{data.get('conid')}"
        return data

