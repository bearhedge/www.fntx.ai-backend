import pyotp
from django.core.exceptions import MultipleObjectsReturned
from django.template.loader import render_to_string

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status

from rest_framework import permissions, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.authentication import JWTAuthentication

from django_filters.rest_framework import DjangoFilterBackend

from accounts.models import CustomUser
from accounts.serializers import UserRegistrationSerializer, UserListSerializer, UserTokenObtainPairSerializer, \
    ChangePasswordSerializer, SendOTPSerializer, ForgotPasswordSerializer
from core.common_utils import send_email

@extend_schema(tags=["Authorization"])
class SignUpView(generics.CreateAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = UserRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User created successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@extend_schema(tags=["User"])
class UserRegistrationView(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserRegistrationSerializer
    authentication_classes = [JWTAuthentication]
    http_method_names = ["get", "post", "patch", "delete"]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["email", "username"]

    def get_queryset(self):
        return CustomUser.objects.filter(is_active=True)

    def list(self, request):
        """
        All client listing and if client not exists then it send empty list
        """
        queryset = self.get_queryset().exclude(id=request.user.id)
        if queryset:
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = UserListSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
        else:
            return Response([], status=status.HTTP_200_OK)

    def create(self, request):
        data = request.data
        serializer = self.serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        serializer = self.serializer_class(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data, status=status.HTTP_200_OK)


class UserObtainTokenPairView(TokenObtainPairView):
    serializer_class = UserTokenObtainPairSerializer

    @extend_schema(tags=["Authorization"])
    def post(self, request, *args, **kwargs):
        """Login user with email and password."""
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

@extend_schema(tags=["Authorization"])
class SendForgotPasswordEmail(APIView):
    serializer_class = SendOTPSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        totp = pyotp.TOTP("base32secret3232")
        otp = totp.now()
        email = serializer.validated_data.get("email")
        host = f"{request.scheme}://{request.META['HTTP_HOST']}"

        CustomUser.objects.filter(email__icontains=email).update(
            otp=otp
        )
        html_message = render_to_string('emails/otp_email_template.html', {'otp': otp, 'host': host})

        send_email(
            "OTP Verification for FINTX",
            "",
            [email],
            html_message
        )
        return Response({"status": "OTP sent successfully."}, status=status.HTTP_200_OK)

@extend_schema(tags=["Authorization"])
class ResetPassword(APIView):
    """
        This function help user to reset the password
        before login.
        Validating otp sent on email.

    """
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data.get("otp")
        email = serializer.validated_data.get("email")
        password = serializer.validated_data.get("password")
        try:
            user_obj = CustomUser.objects.get(email__icontains=email)
        except MultipleObjectsReturned:
            return Response(
                {"error": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "You've entered wrong email address"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user_obj.otp == otp:
            user_obj.set_password(password)
            user_obj.otp = ""
            user_obj.save()
            return Response(
                {"success": "Password has been changed successfully"},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"error": "OTP verification failed. Please enter valid OTP"},
                status=status.HTTP_406_NOT_ACCEPTABLE,
            )
@extend_schema(tags=["Authorization"])
class ChangePasswordViews(generics.CreateAPIView):
    """
    This function help user to change the password
    after login.
    Validating user old password.

    """

    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Password updated successfully"}, status=status.HTTP_200_OK
        )


def page_not_found_view(request, exception):
    return render(request, "404.html", status=404)


def Bad_Gateway(request, exception):
    return render(request, "502.html", status=404)
