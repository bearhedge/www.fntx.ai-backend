from django.urls import re_path
from ibkr.consumers import StrikesConsumer, StreamOptionData, ChartsData, TradeManagementConsumer

websocket_urlpatterns = [
    re_path(r'ws/strikes', StrikesConsumer.as_asgi()),
    re_path(r'trades-management', TradeManagementConsumer.as_asgi()),
    re_path(r'option-stream/strikes', StreamOptionData.as_asgi()),
    re_path(r'option-stream/candle-stick', ChartsData.as_asgi())
]
