import requests
from django.conf import settings
from rest_framework import serializers
from ibkr.utils import fetch_trailing_prices_from_json, compute_returns, calculate_statistics, compute_expected_range
from ibkr.models import TimerData, OnBoardingProcess, SystemData, OrderData, TradingStatus ,Instrument


class OnboardingSerailizer(serializers.ModelSerializer):

    class Meta:
        model = OnBoardingProcess
        exclude = ('periodic_task',)
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


class TimerDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimerData
        fields = ['timer_value', 'start_time']

class TimerDataListSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimerData
        fields = '__all__'



class UpperLowerBoundSerializer(serializers.Serializer):
    time_frame = serializers.ChoiceField(choices=SystemData.TIME_FRAME_CHOICES)
    time_steps = serializers.IntegerField()
    conid = serializers.IntegerField()

    def validate(self, data):
        time_frame_mapping = dict(SystemData.TIME_FRAME_CHOICES)
        time_frame = data.get('time_frame')
        time_steps = data.get('time_steps')

        # Ensure `time_frame` is valid
        if time_frame not in time_frame_mapping:
            raise serializers.ValidationError("Invalid time frame.")

        # Ensure `time_steps` is positive
        if time_steps <= 0:
            raise serializers.ValidationError("Time steps must be a positive integer.")

        # Map to the appropriate period format (e.g., '10D' for 10 days)
        time_unit = time_frame_mapping[time_frame]
        data['period'] = f"{time_steps}{time_unit}"
        print (data['period'])
        return data

    def get_market_data(self, conid, period):
        print(f"Fetching market data for conid: {conid}, period: {period}")

        base_url = settings.IBKR_BASE_URL + "/iserver/marketdata/history"

        tickle_url = "https://localhost:5000/v1/api/tickle"
        response = requests.get(tickle_url, verify=False)

        if response.status_code != 200:
            raise serializers.ValidationError("Failed to fetch session token. Please check the tickle API.")

        try:
            data = response.json()
            session_token = data["session"]
        except (KeyError, ValueError):
            raise serializers.ValidationError("Invalid response from tickle API.")

        # Prepare parameters for the market data API
        params = {
            'conid': conid,
            'period': period,
            'session': session_token
        }

        response = requests.get(base_url, params=params)

        if response.status_code == 200:
            prices = fetch_trailing_prices_from_json(response.json)
            returns = compute_returns(prices)
            mean_return, std_dev_return = calculate_statistics(returns)
            latest_price = prices.iloc[-1]

            range_upper, range_lower = compute_expected_range(latest_price, std_dev_return)

            return {
                "upper_bound": range_upper,
                "lower_bound": range_lower
            }
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

    # def calculate_bounds(self):
    #     # Map time frame to number of days
    #     time_frame_mapping = {
    #         '1-day': 1,
    #         '4-hours': 1/6,
    #         '1-hour': 1/24,
    #         '30-mins': 1/48,
    #         '15-mins': 1/96,
    #         '5-mins': 1/288
    #     }
    #     time_frame_days = time_frame_mapping.get(self.validated_data['time_frame'], 0)
    #     num_days = int(self.validated_data['time_steps'] * time_frame_days)
    #
    #     # # Fetch historical prices
    #     # instrument = Instrument.objects.get(conid=self.validated_data['conid'])
    #     prices = fetch_trailing_prices_from_json(response)
    #
    #     # Compute returns and statistics
    #     returns = compute_returns(prices)
    #     mean_return, std_dev_return = calculate_statistics(returns)
    #     latest_price = prices.iloc[-1]
    #
    #     # Calculate upper and lower bounds
    #     range_upper, range_lower = compute_expected_range(latest_price, std_dev_return)
    #     return range_upper, range_lower