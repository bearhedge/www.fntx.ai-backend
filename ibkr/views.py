import json
from datetime import timedelta

import requests
import pandas as pd
import numpy as np

from collections import defaultdict

from django.conf import settings
from django.utils import timezone
from django.utils.timezone import now
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets

from core.constants import ACCOUNT_SUMMARY_KEYS
from core.exceptions import IBKRAPIError
from core.views import IBKRBase
from ibkr.models import OnBoardingProcess, TradingStatus, Instrument, TimerData, SystemData, PlaceOrder
from ibkr.serializers import UpperLowerBoundSerializer, TimerDataSerializer, OnboardingSerailizer, SystemDataSerializer, \
    TradingStatusSerializer, InstrumentSerializer, TimerDataListSerializer, \
    SystemDataListSerializer, HistoryDataSerializer, PlaceOrderSerializer, PlaceOrderListSerializer, \
    UpdateOrderSerializer, DashBoardSerializer
from ibkr.utils import fetch_bounds_from_json, transform_ibkr_data
from ibkr.tasks import place_orders_task


@extend_schema(tags=["IBKR"])
class AuthStatusView(APIView, IBKRBase):
    """
    API endpoint to check IBKR authentication status.
    """
    permission_classes = [IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        IBKRBase.__init__(self)

    def get(self, request):
        try:
            response = self.auth_status()
            user = request.user

            if response.get('success'):
                if response.get('data').get('authenticated'):
                    onboarding_process, _ = OnBoardingProcess.objects.update_or_create(
                        user=user, defaults={"authenticated": True}
                    )
                    if onboarding_process.periodic_task:
                        onboarding_process.periodic_task.enabled = True
                        onboarding_process.periodic_task.save()

                    return Response(response.get('data'), status=status.HTTP_200_OK)

                else:
                    # Disable the task if the user is not authenticated with client portal
                    onboarding_process, _ = OnBoardingProcess.objects.update_or_create(
                        user=user, defaults={"authenticated": False}
                    )
                    if onboarding_process.periodic_task:
                        onboarding_process.periodic_task.enabled = False
                        onboarding_process.periodic_task.save()

            return Response(
                {"error": response.get("error")}, status=response.get("status")
            )

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": "Error connecting to IBKR API", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(tags=["IBKR"])
class AccountSummaryView(APIView, IBKRBase):
    permission_classes = [IsAuthenticated]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        IBKRBase.__init__(self)

    def get(self, request, *args, **kwargs):
        try:
            response = self.account_summary()
            if response.get('success'):
                data = response.get('data', {})

                # Filter the data to include only the required keys
                filtered_data = {key: data.get(key) for key in ACCOUNT_SUMMARY_KEYS if key in data}

                return Response(filtered_data, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"error": "Failed to fetch account summary"},
                    status=response.get("status")
                )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(tags=["Platform Requirements"])
class OnboardingView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch']
    serializer_class = OnboardingSerailizer

    def get_queryset(self):
        return OnBoardingProcess.objects.all()

    @extend_schema(summary="Get onboarding details for the authenticated user")
    @action(detail=False, methods=["get"], url_path="user-onboarding", url_name="user_onboarding")
    def user_onboarding(self, request):
        """
        Retrieve the onboarding details for the authenticated user.
        """
        ibkr = IBKRBase()
        authentication = ibkr.auth_status()
        if not authentication.get('success'):
            authenticated = False
        elif authentication.get('success') and not authentication.get('data').get('authenticated'):
            authenticated = False
        else:
            authenticated = True
        user = request.user
        try:
            instance = OnBoardingProcess.objects.get(user=user)
            if not instance.authenticated:
                instance.authenticated = authenticated
                instance.save()

                periodic_task = instance.periodic_task
                periodic_task.enabled = True
                periodic_task.save()
        except OnBoardingProcess.DoesNotExist:
            return Response(
                {
                    "authenticated": None,
                    "level_4_permission": None,
                    "active_subscription": None,
                    "metamask_address": None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Serialize the instance
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["SYSTEM"])
class SystemDataView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SystemDataSerializer
    serializer_list_class = SystemDataListSerializer
    queryset = SystemData.objects.all()

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return self.serializer_class
        return self.serializer_list_class

    def list(self, request, *args, **kwargs):
        ibkr = IBKRBase()
        authentication = ibkr.auth_status()
        if not authentication.get('success'):
            authenticated = False
        elif authentication.get('success') and not authentication.get('data').get('authenticated'):
            authenticated = False
        else:
            authenticated = True
        if not authenticated:
            return Response({"error": "You have been logout from IBKR client portal. Please login to continue."}, status=status.HTTP_400_BAD_REQUEST)
        queryset = self.get_queryset().filter(user=request.user, created_at__date=now().date()).first()
        if not queryset:
            return Response({"error": "Not found."}, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        ibkr = IBKRBase()
        authentication = ibkr.auth_status()
        if not authentication.get('success'):
            authenticated = False
        elif authentication.get('success') and not authentication.get('data').get('authenticated'):
            authenticated = False
        else:
            authenticated = True
        if not authenticated:
            return Response({"error": "You have been logout from IBKR client portal. Please login to continue."},
                            status=status.HTTP_400_BAD_REQUEST)
        data = request.data
        data["user"] = request.user.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        try:
            ibkr = IBKRBase()
            authentication = ibkr.auth_status()
            if not authentication.get('success'):
                authenticated = False
            elif authentication.get('success') and not authentication.get('data').get('authenticated'):
                authenticated = False
            else:
                authenticated = True
            if not authenticated:
                return Response({"error": "You have been logout from IBKR client portal. Please login to continue."},
                                status=status.HTTP_400_BAD_REQUEST)
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            data = request.data
            data["user"] = request.user.id
            serializer = self.get_serializer(instance, data=data, partial=partial)
            if serializer.is_valid():
                self.perform_update(serializer)
                return Response(serializer.data)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e.args)}, status=status.HTTP_400_BAD_REQUEST)





@extend_schema(tags=["IBKR"])
class TradingStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            trading_status = TradingStatus.objects.get(user=request.user)
            return Response({
                'status': trading_status.status,
                'wait_time': trading_status.wait_time
            }, status=status.HTTP_200_OK)
        except TradingStatus.DoesNotExist:
            return Response({'error': 'Trading status not found'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        serializer = TradingStatusSerializer(data=request.data)
        if serializer.is_valid():
            trading_status, created = TradingStatus.objects.update_or_create(
                user=request.user,
                defaults=serializer.validated_data
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(tags=["IBKR"])
class InstrumentListCreateView(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch']
    serializer_class = InstrumentSerializer
    queryset = Instrument.objects.all()


    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        grouped_data = defaultdict(list)
        for instrument in serializer.data:
            grouped_data[instrument["instrument_type"]].append({'id': instrument['id'], 'instrument': instrument["instrument"]})

        response_data = {key: value for key, value in grouped_data.items()}

        return Response(response_data, status=status.HTTP_200_OK)

@extend_schema(tags=["Timing"])
class TimerDataViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = TimerData.objects.all()
    serializer_class = TimerDataSerializer
    list_serializer_class = TimerDataListSerializer
    http_method_names = ['get', 'post']

    def get_serializer_class(self):
        if self.action == 'list':
            return self.list_serializer_class
        return self.serializer_class

    def list(self, request):
        timer = TimerData.objects.filter(user=request.user, created_at=timezone.now()).first()
        if timer:
            serializer = self.get_serializer(timer)
            return Response(serializer.data)
        return Response({"error": "No TimerData found"}, status=404)

    def create(self, request):
        today = now().date()
        if TimerData.objects.filter(user=request.user, created_at__date=today).exists():
            return Response({"error": "Timer already set for today."}, status=status.HTTP_400_BAD_REQUEST)
        system_instance = SystemData.objects.filter(user=request.user, created_at__date=today).first()

        data = request.data
        data['original_timer_value'] = data.get('timer_value')
        data['timer_value'] = data.get('timer_value') - 1
        data['original_time_start'] = data.get('start_time')
        data['system_data'] = system_instance.id
        serializer = TimerDataSerializer(data=request.data)
        if serializer.is_valid():
            timer = serializer.save(user=request.user)

            current_date = timezone.now().strftime("%Y-%m-%d")
            task_name = f"Update Timer for {timer.id} - {request.user.username} - {current_date}"

            # Create a periodic task for the timer
            schedule, _ = IntervalSchedule.objects.get_or_create(
                every=1,
                period=IntervalSchedule.MINUTES
            )
            task = PeriodicTask.objects.create(
                interval=schedule,
                name=task_name,
                task="ibkr.tasks.update_timer"
            )

            timer.place_order = "P"
            timer.save()
            task.args = json.dumps([str(timer.id), str(task.id)])
            task.save()

            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


@extend_schema(tags=["IBKR"],
               parameters=[OpenApiParameter(name="symbol", description="Stock symbol", required=True, type=str)])
class SymbolDataView(APIView, IBKRBase):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        IBKRBase.__init__(self)

    def get(self, request):
        try:
            symbol = request.query_params.get('symbol')
            if not symbol:
                return Response({'error': 'Symbol parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
            response = self.auth_status()
            if response.get('success'):
                if response.get('data').get('authenticated'):
                    search_spy_data = self.get_spy_conId(symbol)
                    return Response(search_spy_data, status=status.HTTP_200_OK)
                else:
                    return Response({'error': 'Unable to authenticate with IBKR API. Please login on client portal. '}, status=status.HTTP_400_BAD_REQUEST)

            return Response({'error': response.get('error')}, status=response.get('status'))
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": "Error connecting to IBKR API", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=["IBKR"])
class RangeDataView(APIView, IBKRBase):
    permission_classes = [IsAuthenticated]
    serializer_class = UpperLowerBoundSerializer
    http_method_names = ['post']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        IBKRBase.__init__(self)

    def get_market_data(self, conid, bar):
        """
        Fetch market data using the 'bar' parameter.
        """
        base_url = settings.IBKR_BASE_URL + "/iserver/marketdata/history"

        try:
            data = self.tickle()
            session_token = data['data']['session']
        except (KeyError, ValueError):
            raise IBKRAPIError("Failed to retrieve session token from Tickle API response.")
        params = {
            'conid': conid,
            'period': '2w',
            'bar': bar,
            'session': session_token
        }
        try:
            response = requests.get(base_url, params=params, verify=False)
            if response.status_code == 200:
                return response.json()  # Return raw JSON data
            else:
                raise IBKRAPIError(f"Failed to fetch market data. Status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            raise IBKRAPIError(f"Market data API error: {str(e)}")

    def process_market_data(self, market_data, num_days):
        """
        Process market data using pandas and numpy to compute the desired statistics.
        """
        # Convert market data to a DataFrame
        if market_data:
            try:
                df = pd.DataFrame(market_data['data'])
                df['date'] = pd.to_datetime(df['t'], unit='ms')
                df.set_index('date', inplace=True)
            except Exception as e:
                return {"error": "Unable to calculate the upper and lower bound with the given timeframe."}

            closing_prices = df['c']

            closing_prices = closing_prices.tail(num_days)

            daily_returns = closing_prices.pct_change().dropna()

            std_dev_return = daily_returns.std()


            # Compute the expected price range
            latest_price = closing_prices.iloc[-1]
            range_upper = latest_price * (1 + std_dev_return)
            range_lower = latest_price * (1 - std_dev_return)

            return {
                "upper_bound": round(range_upper, 2),
                "lower_bound": round(range_lower, 2)
            }
        else:
            return {"error": "No data found for the given time."}

    def post(self, request):
        """
        Handle the POST request to fetch market data and calculate statistics.
        """
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            # Fetch the system data for the logged-in user
            system_data_obj = SystemData.objects.filter(user=request.user).first()
            if system_data_obj:
                conid = system_data_obj.ticker_data.get('conid')
                bar = serializer.validated_data['bar']
                time_steps = serializer.validated_data['time_steps']
                try:
                    # Fetch raw market data
                    market_data = self.get_market_data(conid, bar)

                    # Process the data and calculate statistics
                    statistics = self.process_market_data(market_data, time_steps)
                    return Response(statistics, status=status.HTTP_200_OK)
                except IBKRAPIError as e:
                    return Response(
                        {"error": str(e)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                except ValueError as e:
                    return Response(
                        {"error": str(e)},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                return Response({'error': "No System Data found for the logged-in user."}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



@extend_schema(tags=["History Data"])
class GetHistoryDataView(APIView, IBKRBase):
    permission_classes = [IsAuthenticated]
    serializer_class = HistoryDataSerializer

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        IBKRBase.__init__(self)

    def post(self, request):
        bound_data = None
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            conid = serializer.validated_data['conid']
            period = serializer.validated_data.get('period')
            bar = serializer.validated_data['bar']
            history_data = self.historical_data(conid, bar, period)
            if history_data.get('success'):
                bound_data = fetch_bounds_from_json(history_data.get('data'))
            else:
                return Response({"error": history_data.get('error')}, status=status.HTTP_400_BAD_REQUEST)

            # Transform the data to match the frontend structure
            formatted_data = transform_ibkr_data(history_data.get('data'))
            return Response({"history_data": formatted_data, "bound_data": bound_data}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Orders"])
class PlaceOrderView(viewsets.ModelViewSet, IBKRBase):
    permission_classes = [IsAuthenticated]
    serializer_class = PlaceOrderSerializer
    serializer_class_update = UpdateOrderSerializer
    serializer_list_class = PlaceOrderListSerializer
    http_method_names = ['post', 'get', 'delete', 'patch']
    queryset = PlaceOrder.objects.all()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        IBKRBase.__init__(self)

    def get_serializer_class(self):
        print(self.action)
        if self.action == 'list':
            return self.serializer_list_class
        elif self.action == 'create':
            return self.serializer_class
        return self.serializer_class_update

    def _check_authentication(self):
        authentication = self.auth_status()
        if not authentication.get('success'):
            authenticated = False
        elif authentication.get('success') and not authentication.get('data').get('authenticated'):
            authenticated = False
        else:
            authenticated = True

        return authenticated

    def create(self, request):
        authenticated = self._check_authentication()
        if not authenticated:
            return Response({"error": "You have been logout from IBKR client portal. Please login to continue."},
                            status=status.HTTP_400_BAD_REQUEST)
        orders_data = request.data.get('order')
        if not isinstance(orders_data, list):
            return Response({"error": "Data should be an array of orders."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=orders_data, many=True)
        if serializer.is_valid():
            place_orders_task.delay(request.user.id, json.dumps(orders_data))
            return Response({"message": "We have started placing your orders."}, status=status.HTTP_200_OK)

        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request, *args, **kwargs):
        put_orders = False
        call_orders = False
        queryset = self.get_queryset()
        date = now().date()

        queryset = queryset.filter(user=request.user, is_cancelled=False, created_at__date=date)

        serializer = self.get_serializer(queryset, many=True)
        for data in serializer.data:
            if data.get('optionType') == 'call':
                call_orders = True
            elif data.get('optionType') == 'put':
                put_orders = True
        return Response({"data":serializer.data, "call_orders": call_orders, "put_orders": put_orders}, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        authenticated = self._check_authentication()
        if not authenticated:
            return Response({"error": "You have been logout from IBKR client portal. Please login to continue."},
                            status=status.HTTP_400_BAD_REQUEST)
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response(data=serializer.data, status=status.HTTP_200_OK)

        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


    def destroy(self, request, *args, **kwargs):
        """
            This method will not delete the order instead it will cancel the order.
        """
        order = self.get_object()
        if order.is_cancelled:
            return Response({"error": f"Order with id {order.id} is already cancelled. "})
        account = None
        acc_response = self.brokerage_accounts()
        if acc_response.get('success'):
            accounts = acc_response.get('data', {}).get('accounts')
            if accounts:
                account = accounts[0]
        else:
            return Response({"error": acc_response.get("error")}, status=status.HTTP_400_BAD_REQUEST)

        if order:
            order_api_payload = order.order_api_response
            order_id = order_api_payload.get("order_id")
            if order_id:
                cancel_order = self.cancelOrder(order_id, account)
                if not cancel_order.get('success'):
                    return Response({"error": f"Unable to delete order with id {order.id}"})
                else:
                    order.order_status = "Cancelled"
                    order.is_cancelled = True
                    order.save()
            else:
                return Response({"error": f"Order with id {order.id} didn't get placed."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["IBKR"])
class IBKRTokenView(APIView, IBKRBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        IBKRBase.__init__(self)

    def get(self, request):
        try:
            data = self.tickle()
            session_token = data['data']['session']
        except (KeyError, ValueError):
            return Response({'error': 'Unable to authenticate with IBKR API. Please login on client portal.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(session_token, status=status.HTTP_200_OK)

@extend_schema(tags=["Dashboard"])
class DashBoardView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DashBoardSerializer
    http_method_names = ['get']

    def get(self, request):
        today = now().date()
        system_data = SystemData.objects.filter(user=request.user).order_by('-created_at').first()

        if system_data is not None:
            serializer = self.serializer_class(system_data, context={'request': request})
            return Response(serializer.data)
        else:
            return Response({"error": "No system data found."}, status=400)



# @extend_schema(tags=["SYSTEM"])
# class ClosePositionView(APIView, IBKRBase):
#     permission_classes = [IsAuthenticated]
#
#     def __init__(self, **kwargs):
#         super().__init__(**kwargs)
#         IBKRBase.__init__(self)
#
#     def post(self, request):
#         data = request.data
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

