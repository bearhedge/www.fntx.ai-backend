import json

from channels.generic.websocket import AsyncWebsocketConsumer
from urllib.parse import parse_qs
from accounts.models import CustomUser
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async

from .views import IBKRBase



class BaseConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        self.ibkr = IBKRBase()
        self.userObj = None
        super().__init__(*args, **kwargs)

    async def connect(self):
        # Extract token from query parameters
        query_params = parse_qs(self.scope["query_string"].decode())
        user_id = query_params.get("user_id", [None])[0]
        if not user_id:
            await self.send(text_data=json.dumps({"error": "User is not authenticated.", "authentication": False}))
            await self.close()
            return

        self.userObj = await self.get_user_from_token(user_id)
        if isinstance(self.userObj, AnonymousUser):
            await self.send(text_data=json.dumps({"error": "Invalid user token.", "authentication": False}))
            await self.close()
            return

        await self.accept()
        self.keep_running = True

    async def ticker_contract(self, ticker):
        contracts = self.ibkr.get_spy_conId(ticker)
        if contracts.get('success'):
            for contract in contracts:
                for section in contract.get('sections', []):
                    if section.get('secType') == 'OPT':
                        months = section.get("months").split(';')
                        if months:
                            month = months[0]

                        return contract.get('conid'), month

        return None

    @database_sync_to_async
    def get_user_from_token(self, user_id):
        """
            Return the authenticated user.
        """
        try:
            return CustomUser.objects.get(id=user_id)
        except Exception:
            return AnonymousUser()
