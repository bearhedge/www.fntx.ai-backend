from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import UserRegistrationView, ChangePasswordViews, SendForgotPasswordEmail, ResetPassword

router = DefaultRouter()
router.register("user", UserRegistrationView)


urlpatterns = [
    path("change-password/", ChangePasswordViews.as_view(), name="change_password"),
    path("send-otp/", SendForgotPasswordEmail.as_view(), name="sendotp"),
    path("reset-password/", ResetPassword.as_view(), name="reset-password"),
    path("", include(router.urls)),
]
