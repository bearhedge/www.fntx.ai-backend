from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AccountSummaryView, AuthStatusView, OnboardingView, Subscription

router = DefaultRouter()
router.register("onboarding", OnboardingView, "onboarding")


urlpatterns = [
    path('auth-status/', AuthStatusView.as_view(), name='auth_status'),
    path('account_summary/', AccountSummaryView.as_view(), name='account_summary'),
    path('subscription/', Subscription.as_view(), name='subscription'),
    path("", include(router.urls)),

]