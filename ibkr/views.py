import json
import requests

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

from core.exceptions import IBKRAPIError
from core.views import IBKRBase
from ibkr.models import OnBoardingProcess, TradingStatus, Instrument, TimerData, SystemData, PlaceOrder
from ibkr.serializers import UpperLowerBoundSerializer, TimerDataSerializer, OnboardingSerailizer, SystemDataSerializer, \
    TradingStatusSerializer, InstrumentSerializer, TimerDataListSerializer, \
    SystemDataListSerializer, HistoryDataSerializer, PlaceOrderSerializer, PlaceOrderListSerializer
from ibkr.utils import fetch_bounds_from_json
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
class AccountSummaryView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        try:
            ibkr_base_url = settings.IBKR_BASE_URL
            account_id = "U15796707"
            response = requests.get(f"{ibkr_base_url}/portfolio/{account_id}/summary", verify=False)

            if response.status_code == 200:
                return Response(response.json(), status=status.HTTP_200_OK)
            else:
                return Response(
                    {"error": "Failed to fetch account summary"},
                    status=response.status_code
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
        queryset = self.get_queryset().filter(user=request.user, created_at__date=now().date()).first()
        if not queryset:
            return Response({"error": "Not found."}, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        data = request.data
        data["user"] = request.user.id
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data
        data["user"] = request.user.id
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)

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
        data = request.data
        data['original_timer_value'] = data.get('timer_value')
        data['timer_value'] = data.get('timer_value') - 1
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

    def get_market_data(self, conid, period):
        base_url = settings.IBKR_BASE_URL + "/iserver/marketdata/history"

        try:
            data = self.tickle()
            session_token = data['data']['session']
        except (KeyError, ValueError):
            raise IBKRAPIError("Failed to retrieve session token from Tickle API response.")

        params = {
            'conid': conid,
            'period': period,
            'session': session_token
        }
        try:
            response = requests.get(base_url, params=params, verify=False)
            if response.status_code == 200:
                return fetch_bounds_from_json(response.json())
        except requests.exceptions.RequestException as e:
            raise IBKRAPIError(f"Market data API error: {str(e)}")

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            system_data_obj = SystemData.objects.filter(user=request.user).first()
            if system_data_obj:
                conid = system_data_obj.ticker_data.get('conid')
                period = serializer.validated_data['period']
                try:
                    bound_data = self.get_market_data(conid, period)
                    return Response(bound_data, status=status.HTTP_200_OK)
                except IBKRAPIError as e:
                    return Response(
                        {"error": str(e)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                return Response(bound_data, status=status.HTTP_200_OK)
        else:
            return Response({'error': "No System Data found for the logged in user."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["IBKR"])
class GetHistoryDataView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = HistoryDataSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            conid = serializer.validated_data['conid']
            period = serializer.validated_data['period']
            history_data = serializer.get_market_data(conid, period)
            return Response(history_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["Orders"])
class PlaceOrderView(viewsets.ModelViewSet, IBKRBase):
    permission_classes = [IsAuthenticated]
    serializer_class = PlaceOrderSerializer
    serializer_list_class = PlaceOrderListSerializer
    http_method_names = ['post', 'get']
    queryset = PlaceOrder.objects.all()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        IBKRBase.__init__(self)

    def get_serializer_class(self):
        if self.action == 'list':
            return self.serializer_list_class
        return self.serializer_class

    def create(self, request):
        orders_data = request.data.get('order')
        if not isinstance(orders_data, list):
            return Response({"error": "Data should be an array of orders."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=orders_data, many=True)
        if serializer.is_valid():
            place_orders_task.delay(request.user.id, json.dumps(orders_data))
            return Response({"message": "We have started placing your orders."}, status=status.HTTP_200_OK)

        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


    def list(self, request, *args, **kwargs):
        ibkr_orders = []
        queryset = self.get_queryset()
        queryset = queryset.filter(user=request.user, is_deleted=False)
        serializer = self.get_serializer(queryset, many=True)
        ibkr_orders_response = self.retrieveOrders()
        if ibkr_orders_response.get('success'):
            ibkr_orders = ibkr_orders_response.get('data')
        return Response({"ibkr_orders": ibkr_orders, "data":serializer.data}, status=status.HTTP_200_OK)

    @extend_schema(summary="Cancel a placed order")
    @action(detail=False, methods=["post"], url_path="cancel", url_name="cancel")
    def cancel_order(self, request):
        """
        Cancels a placed order based on cOID and orderId received from the frontend.
        """
        cOID = request.data.get("cOID")
        order_id = request.data.get("orderId")
        account_id = request.data.get("accountId")

        if not cOID or not order_id or not account_id:
            return Response(
                {"detail": "All cOID, orderId, accountId are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order = PlaceOrder.objects.get(customer_order_id=cOID)

            cancel_response = self.cancelOrder(order_id, account_id)

            if cancel_response.get("success"):
                order.is_deleted = True
                order.save()

                return Response(
                    {"detail": f"Order {cOID} with orderId {order_id} has been cancelled successfully."},
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "detail": f"Failed to cancel order {cOID} with orderId {order_id}.",
                        "error": cancel_response.get("message"),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except PlaceOrder.DoesNotExist:
            return Response(
                {"detail": f"Order with cOID {cOID} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"detail": "An unexpected error occurred.", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )



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

