from django.urls import re_path
from ibkr.consumers import StrikesConsumer

websocket_urlpatterns = [
    re_path(r'ws/strikes', StrikesConsumer.as_asgi()),
]
