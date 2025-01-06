import requests
import asyncio
import json

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.utils.timezone import now


from channels.generic.websocket import AsyncWebsocketConsumer

from accounts.models import CustomUser
from core.views import IBKRBase
from .models import Strikes, TimerData

from datetime import datetime
from asgiref.sync import sync_to_async


class StrikesConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        self.ibkr = IBKRBase()
        self.strike_data_list = []
        self.place_order_value = None
        self.userObj = None
        self.keep_running = False
        super().__init__(*args, **kwargs)

    async def connect(self):
        # Extract token from query parameters
        query_params = parse_qs(self.scope["query_string"].decode())
        user_id = query_params.get("user_id", [None])[0]
        if not user_id:
            await self.send(text_data=json.dumps({"error": "User is not authenticated.", "authentication": False}))
            await self.close()

        self.userObj = await self.get_user_from_token(user_id)
        await self.accept()
        self.keep_running = True
        asyncio.create_task(self.send_place_order_updates())



    async def disconnect(self, close_code):
        # Stop the background task when the WebSocket disconnects
        self.keep_running = False


    async def receive(self, text_data):
        # Parse received JSON data
        data = json.loads(text_data)
        contract_id = data.get("contract_id")
        authentication = self.ibkr.auth_status()
        if not authentication.get("success"):
            await self.send(text_data=json.dumps({"authentication": False, "error": "You are not authenticated with IBKR. Please login first."}))
            return
        if not contract_id:
            await self.send(text_data=json.dumps({"error": "contract_id is a required parameter.", "authentication": True}))
            return

        strikes = await sync_to_async(list)(
            Strikes.objects.filter(contract_id=contract_id)
        )

        # Group strikes by strike price and process each group
        for strike_price, strike_group in self.group_strikes_by_price(strikes).items():
            processed_data = await self.process_strike(contract_id, strike_price, strike_group)
            if processed_data:
                await self.send(text_data=json.dumps({"option_chain_data": processed_data, "error": None, "authentication": True}))
            else:
                await self.send(text_data=json.dumps({"option_chain_data": processed_data, "error": "Unable to process strikes.", "authentication": False}))

            # Yield control to allow the WebSocket to send the data
            await asyncio.sleep(0)


        # Schedule periodic updates for live data
        asyncio.create_task(self.update_live_data())

    @database_sync_to_async
    def get_user_from_token(self, user_id):
        """
        Decode the JWT token and return the authenticated user.
        """
        try:
            return CustomUser.objects.get(id=user_id)
        except Exception:
            return AnonymousUser()

    def group_strikes_by_price(self, strikes):
        """
        Group strikes by their strike price.
        Each group will contain both 'call' and 'put' for the same price.
        """
        grouped = {}
        for strike in strikes:
            grouped.setdefault(strike.strike_price, []).append(strike)
        return grouped

    async def process_strike(self, contract_id, strike_price, strike_group):
        """
        Process a single strike price and fetch both CALL and PUT data in one API call.
        """
        # Get both CALL and PUT data in a single API call
        # Initialize a new strike entry
        strike_entry = {"strike": strike_price, "call": None, "put": None}
        for strike in strike_group:
            response = await self.fetch_strike_info(contract_id, strike_price, strike)
            if not response.get("success"):
                return []


            # Process CALL and PUT data
            for obj in response["data"]:
                maturity_date = obj.get("maturityDate")
                if maturity_date and int(maturity_date) == int(datetime.now().strftime("%Y%m%d")):
                    live_data = await self.fetch_live_data(obj.get("conid"))
                    if obj.get("right") == "C":
                        strike_entry["call"] = {
                            "conid": obj.get("conid"),
                            "desc2": obj.get("desc2"),
                            "live_data": live_data,
                        }
                    elif obj.get("right") == "P":
                        strike_entry["put"] = {
                            "conid": obj.get("conid"),
                            "desc2": obj.get("desc2"),
                            "live_data": live_data,
                        }

        if strike_entry.get("call") and strike_entry.get("put"):
            self.strike_data_list.append(strike_entry)

        return self.strike_data_list

    async def fetch_strike_info(self, contract_id, strike_price, strike):
        try:
            return self.ibkr.strike_info(contract_id, strike_price, strike.right, strike.month)
        except Exception as e:
            print(f"Error fetching info for strike {strike_price}: {e}")
            return None

    async def fetch_live_data(self, conid):
        """
        Fetch live data for a given conid using the snapshot API.
        """
        try:
            request_url = f"{self.ibkr.ibkr_base_url}/iserver/marketdata/snapshot?conids={conid}&fields=31,82,83,87,7086,7638,7282"
            response = requests.get(url=request_url, verify=False)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching live data for conid {conid}: {e}")

        return None

    async def update_live_data(self):
        """
        Periodically update live data for all processed strikes.
        """
        authentication = self.ibkr.auth_status()
        if not authentication.get("success"):
            await self.send(
                text_data=json.dumps({"authentication": False, "error": "You are not authenticated with IBKR. Please login first."}))
        while True:
            for strike_entry in self.strike_data_list:
                for option_type in ["call", "put"]:
                    option_data = strike_entry.get(option_type)
                    print("option_data" * 10)
                    print(option_data)
                    if option_data and option_data.get("conid"):
                        live_data = await self.fetch_live_data(option_data["conid"])
                        print(live_data)
                        print("live_data" * 10)
                        option_data["live_data"] = live_data if live_data else []
                await self.send(text_data=json.dumps({
                    "option_chain_data": self.strike_data_list, "error": None, "authentication": True
                }))

            # Wait for 1 second before fetching live data again
            await asyncio.sleep(1)

    async def send_place_order_updates(self):
        while self.keep_running:
            timer_data = await self.fetch_timer_data()

            place_order_value = None
            if timer_data:
                timer_data_obj = timer_data[0]
                place_order_value = timer_data_obj.place_order

            await self.send(text_data=json.dumps({
                "place_order": place_order_value,
                "authentication": True
            }))

            await asyncio.sleep(2)

    @sync_to_async
    def fetch_timer_data(self):
        # This method runs in a synchronous thread to avoid async ORM conflicts
        return list(TimerData.objects.filter(user=self.userObj, created_at__date=now().date()))

