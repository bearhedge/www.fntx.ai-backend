import requests
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets

from core.views import IBKRBase
from ibkr.models import OnBoardingProcess
from ibkr.serializers import OnboardingSerailizer


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
                    create, _ = OnBoardingProcess.objects.update_or_create(user=user, defaults={"authenticated":True})
                    return Response(response.get('data'), status=status.HTTP_200_OK)

                else:
                    create, _ = OnBoardingProcess.objects.update_or_create(user=user, defaults={"authenticated":False})
            return Response({'error': response.get('error')}, status=response.get('status'))

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": "Error connecting to IBKR API", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
class Subscription(AuthStatusView):
    def get(self, request):
        try:
            response = self.auth_status()

            if response.get('success'):
                if response.get('data').get('authenticated'):
                    search_spy_data = self.get_spy_conId()
                    conids = search_spy_data.get("data")[0].get("conid")
                    request_url = f"{self.ibkr_base_url}/iserver/accounts"
                    ll = requests.get(url=request_url, verify=False)
                    print(ll.json())
                    data_url = f"{self.ibkr_base_url}/iserver/marketdata/snapshot?conids=141513582&fields=31,84,86"
                    response = requests.get(url=data_url, verify=False)
                    print(response, "===============")
                    return Response(response.json(), status=status.HTTP_200_OK)


            return Response({'error': response.get('error')}, status=response.get('status'))

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": "Error connecting to IBKR API", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

