from django.urls import path
from .views import AccountSummaryView, AuthStatusView

urlpatterns = [
    path('auth-status/', AuthStatusView.as_view(), name='auth_status'),
    path('account_summary/', AccountSummaryView.as_view(), name='account_summary'),

    # path('market_data/', MarketDataView.as_view(), name='market_data'),
]