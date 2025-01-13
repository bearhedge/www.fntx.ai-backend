import requests
import asyncio
import json

from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from channels.exceptions import StopConsumer
from django.contrib.auth.models import AnonymousUser
from django.utils.timezone import now
from asgiref.sync import sync_to_async


from accounts.models import CustomUser
from core.views import IBKRBase
from .models import Strikes, TimerData



class StrikesConsumer(AsyncWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ibkr = IBKRBase()
        self.strike_data_list = []
        self.place_order_value = None
        self.userObj = None
        self.keep_running = False
        self.send_place_order_task = None
        self.update_live_data_task = None
        self.fetch_strikes_task = None


    async def connect(self):
        query_params = parse_qs(self.scope["query_string"].decode())
        user_id = query_params.get("user_id", [None])[0]
        if not user_id:
            await self.send(text_data=json.dumps({"error": "User is not authenticated.", "authentication": False}))
            await self.close()
            return

        self.userObj = await self.get_user_from_token(user_id)
        await self.accept()
        self.keep_running = True
        self.send_place_order_task = asyncio.create_task(self.send_place_order_updates())


    async def disconnect(self, code):
        self.keep_running = False

        # Cancel background tasks
        if self.send_place_order_task:
            self.send_place_order_task.cancel()
        if self.fetch_strikes_task:
            self.fetch_strikes_task.cancel()
        if self.update_live_data_task:
            self.update_live_data_task.cancel()

        await self.close()
        await asyncio.sleep(0)

        raise StopConsumer()

    async def receive(self, text_data):
        data = json.loads(text_data)
        contract_id = data.get("contract_id")
        authentication = self.ibkr.auth_status()
        if not authentication.get("success"):
            await self.send(
                text_data=json.dumps(
                    {"authentication": False, "error": "You are not authenticated with IBKR. Please login first."}))
            return
        if not contract_id:
            await self.send(
                text_data=json.dumps({"error": "contract_id is a required parameter.", "authentication": True}))
            return

        self.scope['contract_id'] = contract_id
        strikes = await sync_to_async(list)(
            Strikes.objects.filter(contract_id=contract_id).order_by('strike_price')
        )
        # Schedule initial strike processing
        await self.update_strike_list(contract_id, strikes)
        await asyncio.sleep(0.1)


        self.fetch_strikes_task = asyncio.create_task(self.fetch_strikes_periodically())
        self.update_live_data_task = asyncio.create_task(self.update_live_data())

    async def fetch_strikes_periodically(self):
        """
        Periodically fetch updated strikes from the database and update the strike list.
        """
        while self.keep_running:
            contract_id = self.scope.get("contract_id")
            if contract_id:
                await self.fetch_and_process_strikes(contract_id)
            await asyncio.sleep(15)  # Fetch strikes every 15 seconds

    async def fetch_and_process_strikes(self, contract_id):
        """
        Fetch strikes from the database and process them.
        """
        strikes = await sync_to_async(list)(
            Strikes.objects.filter(contract_id=contract_id).order_by('strike_price')
        )
        await self.update_strike_list(contract_id, strikes)

    async def update_strike_list(self, contract_id, strikes):
        """
        Update the strike list with the latest data from the database.
        Remove any strikes no longer present in the database.
        """
        current_strikes = {strike.strike_price: strike for strike in strikes}
        new_strike_data_list = []

        for strike_entry in self.strike_data_list:
            strike_price = strike_entry["strike"]
            if strike_price in current_strikes:
                new_strike_data_list.append(strike_entry)

        # Update the list and send to the frontend if there are changes
        if self.strike_data_list and new_strike_data_list != self.strike_data_list:
            self.strike_data_list = sorted(new_strike_data_list, key=lambda x: x["strike"])
            await self.send(text_data=json.dumps({
                "option_chain_data": self.strike_data_list,
                "error": None,
                "authentication": True
            }))

        # Add new strikes
        for strike in strikes:
            if strike.strike_price not in [entry["strike"] for entry in new_strike_data_list]:
                await self.process_single_strike(contract_id, strike, new_strike_data_list)
                # Send data immediately after processing each strike
                self.strike_data_list = sorted(new_strike_data_list, key=lambda x: x["strike"])
                await self.send(text_data=json.dumps({
                    "option_chain_data": self.strike_data_list,
                    "error": None,
                    "authentication": True
                }))
                await asyncio.sleep(0.2)

    async def process_single_strike(self, contract_id, strike, strike_list):
        """
        Process a single strike and append it to the list.
        """
        live_data = await self.fetch_live_data(strike.strike_info.get('conid'))
        strike_entry = {"strike": strike.strike_price, "call": None, "put": None}
        if strike.right == "C":
            strike_entry["call"] = {
                "conid": strike.strike_info.get("conid"),
                "desc2": strike.strike_info.get("desc2"),
                "live_data": live_data,
            }
        elif strike.right == "P":
            strike_entry["put"] = {
                "conid": strike.strike_info.get("conid"),
                "desc2": strike.strike_info.get("desc2"),
                "live_data": live_data,
            }
        if strike_entry.get("call") or strike_entry.get("put"):
            strike_list.append(strike_entry)

    async def update_live_data(self):
        """
        Periodically update live data for all processed strikes.
        """
        while self.keep_running:
            for strike_entry in self.strike_data_list:
                for option_type in ["call", "put"]:
                    option_data = strike_entry.get(option_type)
                    if option_data and option_data.get("conid"):
                        live_data = await self.fetch_live_data(option_data["conid"])
                        option_data["live_data"] = live_data if live_data else []
                        await self.send(text_data=json.dumps({
                            "option_chain_data": self.strike_data_list,
                            "error": None,
                            "authentication": True
                        }))
            await asyncio.sleep(0.1)

    @database_sync_to_async
    def get_user_from_token(self, user_id):
        try:
            return CustomUser.objects.get(id=user_id)
        except Exception:
            return AnonymousUser()

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

            await asyncio.sleep(0.5)

    @sync_to_async
    def fetch_timer_data(self):
        # This method runs in a synchronous thread to avoid async ORM conflicts
        return list(TimerData.objects.filter(user=self.userObj, created_at__date=now().date()))

