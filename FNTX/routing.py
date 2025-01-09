from django.urls import re_path
from ibkr.consumers import StrikesConsumer, StreamOptionData

websocket_urlpatterns = [
    re_path(r'ws/strikes', StrikesConsumer.as_asgi()),
    re_path(r'option-stream', StreamOptionData.as_asgi())
]
