import requests
from django.conf import settings
from rest_framework import serializers
from ibkr.utils import fetch_bounds_from_json
from ibkr.models import TimerData, OnBoardingProcess, SystemData, TradingStatus ,Instrument, PlaceOrder
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
        fields = ['timer_value', 'start_time', 'original_timer_value']


class TimerDataListSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimerData
        fields = '__all__'


class SystemDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemData
        fields = "__all__"

class SystemDataListSerializer(serializers.ModelSerializer):
    timer = serializers.SerializerMethodField()
    contract_leg_type = serializers.SerializerMethodField()


    class Meta:
        model = SystemData
        exclude = ('user', )
        depth = 1

    def get_timer(self, obj):
        timer_instace = TimerData.objects.filter(user=obj.user).first()
        serailized_data = TimerDataListSerializer(timer_instace).data
        return serailized_data

    def get_contract_leg_type(self, obj):
        return obj.contract_leg_type


class UpperLowerBoundSerializer(serializers.Serializer):
    time_frame = serializers.ChoiceField(choices=SystemData.TIME_FRAME_CHOICES)  # Validates against predefined choices
    time_steps = serializers.IntegerField()  # Positive integer for time steps

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
        return data



class HistoryDataSerializer(serializers.Serializer, IBKRBase):
    period = serializers.CharField()  # Positive integer for time steps
    conid = serializers.IntegerField()  # Integer representing contract ID

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        IBKRBase.__init__(self)

    def validate(self, data):
        data['period'] = f"{data.get('period')}"
        data['conid'] = data.get('conid')
        return data

    def get_market_data(self, conid, period):
        base_url = settings.IBKR_BASE_URL + "/iserver/marketdata/history"

        try:
            data = self.tickle()
            session_token = data['data']['session']
        except (KeyError, ValueError):
            raise serializers.ValidationError("Invalid response from tickle API.")

        params = {
            'conid': conid,
            'period': period,
            'session': session_token
        }
        response = requests.get(base_url, params=params, verify=False)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            raise serializers.ValidationError("Too many requests. Please try again later.")
        else:
            try:
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise serializers.ValidationError(f"Market data API error: {str(e)}")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        conid = instance.get('conid')
        period = instance.get('period')

        try:
            market_data = self.get_market_data(conid, period)
            data['market_data'] = market_data
        except serializers.ValidationError as e:
            data['market_data_error'] = str(e)
        return data

class PlaceOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceOrder
        fields = ['accountId', 'conid', 'orderType', 'side', 'price', 'tif', 'quantity', 'exp_date', 'exp_time']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)




