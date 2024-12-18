from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import RangeDataView, ContractsView, SymbolDataView, InstrumentListCreateView, AccountSummaryView, \
    AuthStatusView, OnboardingView, SystemDataView, OrderDataView, TimerDataViewSet

router = DefaultRouter()
router.register("onboarding", OnboardingView, "onboarding")
router.register("instruments", InstrumentListCreateView, "instruments")
router.register("timer", TimerDataViewSet, "timer")
router.register("range",RangeDataView,"range")

urlpatterns = [
    path('auth-status/', AuthStatusView.as_view(), name='auth_status'),
    path('account_summary/', AccountSummaryView.as_view(), name='account_summary'),
    path('system-data/', SystemDataView.as_view(), name='system-data'),
    path('order-data/', OrderDataView.as_view(), name='order-data'),
    path('symbol_conid',SymbolDataView.as_view(),name='symbol_conid'),
    path('contracts',ContractsView.as_view(),name='contracts'),
    path('range',RangeDataView.as_view(),name='Range'),
    path("", include(router.urls)),

]