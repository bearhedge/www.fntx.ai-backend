from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import InstrumentDetailView, RangeDataView, MarketDataView, SymbolDataView, InstrumentListCreateView, AccountSummaryView, AuthStatusView, OnboardingView, Subscription, SystemDataView, OrderDataView

router = DefaultRouter()
router.register("onboarding", OnboardingView, "onboarding")

urlpatterns = [
    path('auth-status/', AuthStatusView.as_view(), name='auth_status'),
    path('account_summary/', AccountSummaryView.as_view(), name='account_summary'),
    path('subscription/', Subscription.as_view(), name='subscription'),
    path('system-data/', SystemDataView.as_view(), name='system-data'),
    path('order-data/', OrderDataView.as_view(), name='order-data'),
    path('instruments/', InstrumentListCreateView.as_view(), name='instrument-list-create'),
    path('instruments/<int:id>/', InstrumentDetailView.as_view(), name='instrument-detail'),
    path('symbol_conid',SymbolDataView.as_view(),name='symbol_conid'),
    path('market_data',MarketDataView.as_view(),name='market_data'),
    path('range',RangeDataView.as_view(),name='Range'),
    path("", include(router.urls)),

]