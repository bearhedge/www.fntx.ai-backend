import requests
import asyncio
import json

from channels.generic.websocket import AsyncWebsocketConsumer

from core.views import IBKRBase
from .models import Strikes

from datetime import datetime
from asgiref.sync import sync_to_async


class StrikesConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        self.ibkr = IBKRBase()
        self.strike_data_list = []
        super().__init__(*args, **kwargs)

    async def receive(self, text_data):
        # Parse received JSON data
        data = json.loads(text_data)
        contract_id = data.get("contract_id")
        authentication = self.ibkr.auth_status()
        if not authentication.get("success"):
            await self.send({"authentication": False, "error": "You are not authenticated with IBKR. Please login first."})
            return
        if not contract_id:
            await self.send({"error": "contract_id is a required parameter.", "authentication": True})
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
                {"authentication": False, "error": "You are not authenticated with IBKR. Please login first."})
        while True:
            for strike_entry in self.strike_data_list:
                for option_type in ["call", "put"]:
                    option_data = strike_entry.get(option_type)
                    if option_data and option_data.get("conid"):
                        live_data = await self.fetch_live_data(option_data["conid"])
                        option_data["live_data"] = live_data if live_data else []
                await self.send(text_data=json.dumps({
                    "option_chain_data": self.strike_data_list, "error": None, "authentication": True
                }))

            # Wait for a few seconds before fetching live data again
            await asyncio.sleep(1)

