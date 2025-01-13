import json
import re
from datetime import datetime, timedelta

import requests

from django.conf import settings
from django.utils.timezone import now
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from rest_framework import serializers

from ibkr.models import TimerData, OnBoardingProcess, SystemData, TradingStatus ,Instrument, PlaceOrder
from ibkr.tasks import fetch_and_save_strikes
from core.views import IBKRBase


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
        fields = ['timer_value', 'start_time', 'original_timer_value', 'original_time_start']


class TimerDataListSerializer(serializers.ModelSerializer):
    end_time = serializers.SerializerMethodField()
    class Meta:
        model = TimerData
        fields = '__all__'

    def get_end_time(self, obj):
        today = now().date()
        start_datetime = datetime.combine(today, obj.original_time_start)

        end_datetime = start_datetime + timedelta(minutes=obj.original_timer_value)

        # Format the time as HH:MM
        return end_datetime.strftime('%H:%M')


class SystemDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemData
        fields = "__all__"

    def create(self, validated_data):
        today = now().date()

        ticker_data = validated_data.get('ticker_data')
        user = validated_data.get('user')
        if SystemData.objects.filter(user=user, created_at__date=today).exists():
            raise serializers.ValidationError({"error":"An entry for this user already exists for today."})
        valid_contract = False
        if ticker_data:
            contract_id = ticker_data.get('conid')
            sections = ticker_data.get('sections')
            for section in sections:
                if section.get('secType') == 'OPT':
                    months = section.get("months").split(';')
                    if months:
                        month = months[0]
                        valid_contract = True
                        break
            if not valid_contract:
                raise serializers.ValidationError({"error": "Cannot use this Contract ID as it is not for options trading."})

            if contract_id:
                validated_data['contract_id'] = contract_id

                current_date = datetime.now().strftime("%Y-%m-%d")
                task_name = f"Fetch and Validate Strikes for {contract_id} - {user} - {current_date}"

                schedule, _ = IntervalSchedule.objects.get_or_create(
                    every=1,
                    period=IntervalSchedule.MINUTES
                )

                existing_task = PeriodicTask.objects.filter(name=task_name)
                if existing_task:
                    existing_task.delete()

                task = PeriodicTask.objects.create(
                    interval=schedule,
                    name=task_name,
                    task='ibkr.tasks.fetch_and_save_strikes')

                task.args = json.dumps([contract_id, str(validated_data["user"].id), month, str(today), str(task.id)])
                task.save()
                validated_data['validate_strikes_task'] = task

        created_instance = SystemData.objects.create(**validated_data)

        fetch_and_save_strikes.delay(contract_id, str(validated_data["user"].id), month, str(today), str(task.id))

        return created_instance

    def update(self, instance, validated_data):
        today = now().date()
        task = None
        ticker_data = validated_data.get('ticker_data')
        user = validated_data.get('user')

        valid_contract = False
        month = None
        if ticker_data:
            contract_id = ticker_data.get('conid')
            sections = ticker_data.get('sections')

            for section in sections:
                if section.get('secType') == 'OPT':
                    months = section.get("months").split(';')
                    if months:
                        month = months[0]
                        valid_contract = True
                        break

            if not valid_contract:
                raise serializers.ValidationError({"error": "Cannot use this Contract ID as it is not for options trading"})

            # Update the instance with the new contract_id
            if contract_id and contract_id != instance.contract_id:
                validated_data['contract_id'] = contract_id

                current_date = datetime.now().strftime("%Y-%m-%d")
                task_name = f"Fetch and Validate Strikes for {contract_id} - {user} - {current_date}"
                schedule, _ = IntervalSchedule.objects.get_or_create(
                    every=3,
                    period=IntervalSchedule.MINUTES
                )

                # Update the associated periodic task or create a new one if does not exist
                if instance.validate_strikes_task:
                    task = instance.validate_strikes_task
                    task.interval = schedule
                    task.args = json.dumps([contract_id, str(validated_data["user"].id), month, str(today), str(instance.validate_strikes_task.id)])
                    task.name = task_name
                    task.save()
                else:
                    task = PeriodicTask.objects.create(
                        interval=schedule,
                        name=task_name,
                        task='ibkr.tasks.fetch_and_save_strikes',
                    )
                    task.args = json.dumps([contract_id, str(validated_data["user"]), month, str(today), str(task.id)])
                    task.save()
                    validated_data['validate_strikes_task'] = task

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        if task:
            fetch_and_save_strikes.delay(contract_id, str(validated_data["user"].id), month, str(today), str(task.id))

        return instance

class SystemDataListSerializer(serializers.ModelSerializer):
    timer = serializers.SerializerMethodField()
    contract_leg_type = serializers.SerializerMethodField()

    class Meta:
        model = SystemData
        exclude = ('user', )
        depth = 1

    def get_timer(self, obj):
        timer_instace = TimerData.objects.filter(user=obj.user, created_at__date=now().date()).first()
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
        data['bar'] = f"{numerical_part}{unit_part}"
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
        fields = ['conid', 'price', 'quantity', 'limit_sell', 'stop_loss', 'take_profit', 'optionType']

    def validate(self, data):
        stop_loss = data.get('stop_loss')
        take_profit = data.get('take_profit')
        optionType = data.get('optionType')

        if not (100 <= stop_loss <= 600):
            raise serializers.ValidationError({"error": "Stop loss must be between 100% and 500%."})

        if not (1 <= take_profit <= 50):
            raise serializers.ValidationError({"error": "Take profit must be between 1% and 50%."})

        if not optionType in ['call', 'put']:
            raise serializers.ValidationError({"error": "Option type must be call or put."})

        return data


class PlaceOrderListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceOrder
        fields = "__all__"
        depth = 1

