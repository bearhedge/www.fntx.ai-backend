from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import RangeDataView, SymbolDataView, InstrumentListCreateView, AccountSummaryView, \
    AuthStatusView, OnboardingView, SystemDataView, OrderDataView, TimerDataViewSet, GetHistoryDataView, PlaceOrderView
from .views import RangeDataView, SymbolDataView, InstrumentListCreateView, AccountSummaryView, \
    AuthStatusView, OnboardingView, SystemDataView, OrderDataView, TimerDataViewSet

router = DefaultRouter()
router.register("onboarding", OnboardingView, "onboarding")
router.register("instruments", InstrumentListCreateView, "instruments")
router.register("timer", TimerDataViewSet, "timer")
router.register("place-order",PlaceOrderView,"place-order")
router.register("system-data", SystemDataView, "system-data")

urlpatterns = [
    path('auth-status/', AuthStatusView.as_view(), name='auth_status'),
    path('account_summary/', AccountSummaryView.as_view(), name='account_summary'),
    path('order-data/', OrderDataView.as_view(), name='order-data'),
    path('symbol_conid',SymbolDataView.as_view(),name='symbol_conid'),
    path('history_data',GetHistoryDataView.as_view(), name='history_data'),
    # path('contracts',ContractsView.as_view(),name='contracts'),
    path('range',RangeDataView.as_view(),name='Range'),
    path("", include(router.urls)),

]