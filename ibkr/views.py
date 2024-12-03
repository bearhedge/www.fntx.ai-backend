from http.client import responses

import requests
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from core.views import IBKRBase
from ibkr.models import OnBoardingProcess


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
                else:
                    create, _ = OnBoardingProcess.objects.update_or_create(user=user, defaults={"authenticated":False})

                return Response(response['data'], status=status.HTTP_200_OK)
            else:
                return Response({'error': response['error']}, status=response["status"])

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


# class MarketDataView(APIView):
#     def get(self, request, *args, **kwargs):
#         con_id = request.query_params.get('con_id')
#         if not con_id:
#             return Response({'error': 'ConId parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
#         try:
#             data = get_market_data(int(con_id))
#             return Response({'data': data}, status=status.HTTP_200_OK)
#         except Exception as e:
#             return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)