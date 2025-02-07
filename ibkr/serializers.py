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
        fields = ['timer_value', 'start_time', 'original_timer_value', 'original_time_start', 'system_data']


class TimerDataListSerializer(serializers.ModelSerializer):
    end_time = serializers.SerializerMethodField()
    class Meta:
        model = TimerData
        fields = '__all__'

    def get_end_time(self, obj):
        today = now().date()
        start_datetime = datetime.combine(today, obj.original_time_start)

        end_datetime = start_datetime + timedelta(minutes=obj.original_timer_value)

        return end_datetime.strftime('%H:%M:%S.%f')


class SystemDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemData
        fields = "__all__"

    def create(self, validated_data):
        ibkr = IBKRBase()
        today = now().date()
        contract_id = None
        ticker = None
        symbol = validated_data.pop('ticker_data')
        user = validated_data.get('user')
        if SystemData.objects.filter(user=user, created_at__date=today).exists():
            raise serializers.ValidationError({"error":"An entry for this user already exists for today."})
        valid_contract = False
        if symbol:
            search_spy_data = ibkr.get_spy_conId(symbol)
            data = search_spy_data.get('data') if search_spy_data.get('success') else []
            if data:
                for ticker_data in data:
                    ticker = ticker_data
                    contract_id = ticker_data.get('conid')
                    sections = ticker_data.get('sections')
                    for section in sections:
                        if section.get('secType') == 'OPT':
                            months = section.get("months").split(';')
                            if months:
                                month = months[0]
                                valid_contract = True
                                break
                    if valid_contract:
                        break
            validated_data['contract_month'] = month
            if not valid_contract:
                raise serializers.ValidationError({"error": "Cannot use this Contract ID as it is not for options trading."})

            if contract_id:
                validated_data['contract_id'] = contract_id
                validated_data['ticker_data'] = ticker

        created_instance = SystemData.objects.create(**validated_data)

        return created_instance

    def update(self, instance, validated_data):
        symbol = validated_data.pop('ticker_data')
        ibkr = IBKRBase()
        contract_id = None
        ticker = None
        month = None

        valid_contract = False
        if symbol:
            search_spy_data = ibkr.get_spy_conId(symbol)
            data = search_spy_data.get('data') if search_spy_data.get('success') else []
            if data:
                for ticker_data in data:
                    ticker = ticker_data
                    contract_id = ticker_data.get('conid')
                    sections = ticker_data.get('sections')

                    for section in sections:
                        if section.get('secType') == 'OPT':
                            months = section.get("months").split(';')
                            if months:
                                month = months[0]
                                valid_contract = True
                                break
                    if valid_contract:
                        break

            if not valid_contract:
                raise serializers.ValidationError({"error": "Cannot use this Contract ID as it is not for options trading"})

            # Update the instance with the new contract_id
            if contract_id and contract_id != instance.contract_id:
                validated_data['contract_id'] = contract_id
                validated_data['ticker_data'] = ticker
                validated_data['contract_month'] = month

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
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



class HistoryDataSerializer(serializers.Serializer):
    period = serializers.CharField(required=False)
    bar = serializers.CharField()
    conid = serializers.IntegerField()

    def validate(self, data):
        if not data.get('bar'):
            raise serializers.ValidationError({"error": "Bar is required parameter. Please make sure you send it."})
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

class UpdateOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceOrder
        fields = ['conid', 'price', 'quantity', 'limit_sell', 'stop_loss', 'take_profit', 'optionType']

    def update(self, instance, validated_data):
        """
            Modify the order if certain fields are changed.
        """
        # Fields that trigger a modify API call
        if instance.order_status in ['Cancelled', 'pending_cancel']:
            raise serializers.ValidationError({"error": "Cannot modify this order as it has been already cancelled."})
        elif instance.order_status == 'Filled':
            raise serializers.ValidationError({"error": "Cannot modify this order as it has been already filled."})

        fields_to_check = ['limit_sell', 'stop_loss', 'take_profit']
        modified_field = None

        for field in fields_to_check:
            new_value = validated_data.get(field)
            current_value = getattr(instance, field)
            if new_value and new_value != current_value:
                modified_field = field
                break

        if modified_field:
            instance = self.modify_orders(instance, validated_data, modified_field)

        return instance

    def modify_orders(self, instance, validated_data, modified_field):
        """
        Call the IBKR modify order API with the updated fields.
        """
        order_id = instance.order_api_response.get("order_id")
        print(validated_data, modified_field)
        if validated_data.get(modified_field) == 'stop_loss':
            price = instance.price + instance.price * (validated_data.get(modified_field) / 100)
        elif validated_data.get(modified_field) == 'take_profit':
            price = instance.price/100 * validated_data.get(modified_field)
        else:
            price = validated_data.get(modified_field)


        order_data = {
            "acctId": instance.accountId,
            "conid": instance.conid,
            "orderType": instance.orderType,
            "price": price,
            "side": instance.side,
            "tif": instance.tif,
            "quantity": instance.quantity
        }

        ibkr = IBKRBase()
        order_response = ibkr.modifyOrder(order_id, instance.accountId, order_data)
        response = None
        error = None
        order_status = None
        if order_response.get('success'):
            data = order_response.get("data", [])
            if isinstance(data, list) and data:
                order_data = data[0]
                order_id = order_data.get("order_id")
                reply_id = order_data.get("id")
                response = order_data

                # Confirm the order if reply_id is present
                while reply_id:
                    confirm_response = ibkr.replyOrder(reply_id, {"confirmed": True})

                    if not confirm_response.get("success"):
                        error = confirm_response.get("error")
                        break

                    confirm_data = confirm_response.get("data", [])
                    print(confirm_data, "confirm_data")
                    if confirm_data and isinstance(confirm_data, list):
                        confirmed_data = confirm_data[0]
                        order_confirmed_id = confirmed_data.get("order_id")
                        if order_confirmed_id:
                            reply_id = None
                            response = confirmed_data
                        else:
                            reply_id = confirmed_data.get("id")
                    else:
                        data = confirm_response.get("data")
                        if data:
                            error = data.get('error')
                        break
            else:
                error = order_response.get('data')
            if response:
                order_status = response.get("order_status", "")
        else:
            error = order_response.get("error")

        if error:
            raise serializers.ValidationError({"error": "Failed to modify order with IBKR API."})
        instance.order_api_response = response
        if modified_field == 'limit_sell':
            instance.limit_sell = validated_data.get(modified_field)
        elif modified_field == 'stop_loss':
            instance.stop_loss = validated_data.get(modified_field)
        elif modified_field == 'take_profit':
            instance.take_profit = validated_data.get(modified_field)
        instance.order_status = order_status

        instance.save()

        return instance

class PlaceOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceOrder
        fields = ['conid', 'price', 'quantity', 'limit_sell', 'stop_loss', 'take_profit', 'optionType', 'system_data']

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


class DashBoardSerializer(serializers.ModelSerializer):
    orders = serializers.SerializerMethodField()
    timer = serializers.SerializerMethodField()

    class Meta:
        model = SystemData
        exclude = ('user',)
        depth = 1

    def get_timer(self, obj):
        timer_instance = TimerData.objects.filter(system_data=obj).first()
        if timer_instance:
            serailized_data = TimerDataListSerializer(timer_instance).data
            return serailized_data
        return {}

    def get_orders(self, obj):
        request = self.context.get('request')
        user_orders = PlaceOrder.objects.filter(user=request.user, system_data=obj)

        serializer_data = PlaceOrderListSerializer(user_orders, many=True).data
        return serializer_data