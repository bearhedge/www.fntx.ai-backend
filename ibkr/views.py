import json
from collections import defaultdict

import requests
from django.conf import settings
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from core.views import IBKRBase
from ibkr.models import OnBoardingProcess, TradingStatus, Instrument, TimerData
from ibkr.serializers import UpperLowerBoundSerializer, TimerDataSerializer, OnboardingSerailizer, SystemDataSerializer, \
    OrderDataSerializer, TradingStatusSerializer, InstrumentSerializer, TimerDataListSerializer


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
        user = request.user
        try:
            instance = OnBoardingProcess.objects.get(user=user)
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


@extend_schema(tags=["IBKR"])
class SystemDataView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['post']
    serializer_class = SystemDataSerializer

    def post(self, request):
        serializer = SystemDataSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(tags=["IBKR"])
class OrderDataView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['post']
    serializer_class = OrderDataSerializer

    def post(self, request):
        serializer = OrderDataSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    permission_classes = [AllowAny]
    authentication_classes = []
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
        timer = TimerData.objects.filter(user=request.user).first()
        if timer:
            serializer = self.get_serializer(timer)
            return Response(serializer.data)
        return Response({"detail": "No TimerData found"}, status=404)

    def create(self, request):
        serializer = TimerDataSerializer(data=request.data)
        if serializer.is_valid():
            timer = serializer.save(user=request.user)

            # Create a periodic task for the timer
            schedule, _ = IntervalSchedule.objects.get_or_create(
                every=1,
                period=IntervalSchedule.MINUTES
            )

            PeriodicTask.objects.create(
                interval=schedule,
                name=f"Update Timer for {timer.id}",
                task="update_timer",
                args=json.dumps([timer.id]),
            )

            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


@extend_schema(tags=["IBKR"],
               parameters=[OpenApiParameter(name="symbol", description="Stock symbol", required=True, type=str)])
class SymbolDataView(APIView, IBKRBase):
    permission_classes = [IsAuthenticated]

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

            return Response({'error': response.get('error')}, status=response.get('status'))
        except requests.exceptions.RequestException as e:
            return Response(
                {"error": "Error connecting to IBKR API", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )




@extend_schema(tags=["IBKR"])
class MarketDataView(APIView):
    permission_classes = [IsAuthenticated]  # Ensure only authenticated users can access this endpoint
    serializer_class = UpperLowerBoundSerializer  # Associate the serializer with this view

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            try:
                market_data = serializer.to_representation(serializer.validated_data)
                return Response(market_data, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(tags=["IBKR"])
class RangeDataView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UpperLowerBoundSerializer
    http_method_names = ['get', 'post']


    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            range_upper, range_lower = serializer.get_market_data()
            return Response({'upper_bound': range_upper, 'lower_bound': range_lower}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        time_frame = request.query_params.get('time_frame')
        time_steps = request.query_params.get('time_steps')
        conid = request.query_params.get('conid')

        if not all([time_frame, time_steps, conid]):
            return Response({'error': 'time_frame, time_steps, and conid are required parameters'},
                            status=status.HTTP_400_BAD_REQUEST)

        data = {
            'time_frame': time_frame,
            'time_steps': time_steps,
            'conid': conid
        }

        serializer = self.serializer_class(data=data)
        if serializer.is_valid():
            range_upper, range_lower = serializer.get_market_data()
            return Response({'upper_bound': range_upper, 'lower_bound': range_lower}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)