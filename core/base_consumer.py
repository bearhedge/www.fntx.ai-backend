import asyncio
import json
from datetime import datetime

import requests
from channels.exceptions import StopConsumer

from channels.generic.websocket import AsyncWebsocketConsumer
from urllib.parse import parse_qs

from django.utils.timezone import now

from accounts.models import CustomUser
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async

from ibkr.models import SystemData
from .views import IBKRBase


class BaseConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        self.ibkr = IBKRBase()
        self.userObj = None
        self.keep_running = False
        self.month = None
        self.last_day_price = None
        self.update_last_price_task = None
        self.update_live_data_task = None
        self.strike_data_list = []


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

    async def disconnect(self, code):
        self.keep_running = False

        if self.update_last_price_task:
            self.update_last_price_task.cancel()
        if self.update_live_data_task:
            self.update_live_data_task.cancel()

        await self.close()
        raise StopConsumer()

    async def ticker_contract(self, ticker):
        contracts = self.ibkr.get_spy_conId(ticker)
        if contracts.get('success'):
            for contract in contracts.get('data'):
                for section in contract.get('sections', []):
                    if section.get('secType') == 'OPT':
                        months = section.get("months").split(';')
                        if months:
                            month = months[0]

                        return contract.get('conid'), month

        return None, None

    async def fetch_strike_info(self, contract_id, strike_price, strike_type):
        """
        Fetch detailed information for a strike from the IBKR API.
        """
        try:
            return self.ibkr.strike_info(contract_id, strike_price, strike_type, self.month)
        except Exception as e:
            print(f"Error fetching info for strike {strike_price}: {e}")
            return None

    async def fetch_live_data(self, conid):
        """
        Fetch live data for a given conid.
        """
        try:
            response = requests.get(
                f"{self.ibkr.ibkr_base_url}/iserver/marketdata/snapshot?conids={conid}&fields=31,82,83,87,7086,7638,7282",
                verify=False,
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching live data for conid {conid}: {e}")

        return None

    async def fetch_and_validate_strikes(self, contract_id):
        """
        Calculate valid strikes based on the last-day price and fetch live data for these strikes.
        """
        while self.keep_running:
            if not self.last_day_price:
                await asyncio.sleep(0.1)
                continue

            else:
                range_count = 20

                # Simulate fetching strikes from IBKR
                all_strikes = self.ibkr.fetch_strikes(contract_id, self.month)
                if not all_strikes.get('success'):
                    return

                strikes_response = all_strikes.get('data')
                all_call_strikes = strikes_response.get("call", [])
                all_put_strikes = strikes_response.get("put", [])

                call_strikes = [strike for strike in all_call_strikes if strike >= self.last_day_price][:range_count]
                put_strikes = [strike for strike in all_put_strikes if strike <= self.last_day_price][-range_count:]

                valid_strikes = set(call_strikes + put_strikes)
                # Convert self.strike_data_list to a dictionary for easy updates
                current_strike_data = {entry["strike"]: entry for entry in self.strike_data_list}

                for strike in valid_strikes:
                    strike_info = None

                    strike_type = "C" if strike in call_strikes else "P"
                    strike_info_response = await self.fetch_strike_info(contract_id, strike, strike_type)
                    if not strike_info_response.get('success'):
                        continue
                    data = strike_info_response.get('data')
                    for obj in data:
                        maturity_date = obj.get("maturityDate")

                        if maturity_date and int(maturity_date) == int(datetime.now().strftime("%Y%m%d")):
                            strike_info = obj
                            break
                    if strike_info:
                        live_data = await self.fetch_live_data(strike_info.get("conid"))
                        strike_entry = {
                            "last_day_price": self.last_day_price,
                            "strike": strike,
                            "call" if strike_type == 'C' else "put": {
                                "conid": strike_info.get("conid"),
                                "desc2": strike_info.get("desc2"),
                                "live_data": live_data,
                            },
                        }
                        current_strike_data[strike] = strike_entry

                        self.strike_data_list = sorted(current_strike_data.values(), key=lambda x: x["strike"])

                        await self.send(
                            text_data=json.dumps(
                                {"option_chain_data": self.strike_data_list, "error": None, "authentication": True}
                            )
                        )
                        await asyncio.sleep(0)

                for strike in list(current_strike_data.keys()):
                    if strike not in valid_strikes:
                        del current_strike_data[strike]

                self.strike_data_list = sorted(current_strike_data.values(), key=lambda x: x["strike"])
                await asyncio.sleep(0)


    async def update_last_price_periodically(self):
        """
        Periodically fetch the last-day price and update the strike list based on the new price.
        """

        while self.keep_running:
            contract_id = self.scope.get("contract_id")
            if not contract_id:
                await asyncio.sleep(0.1)
                continue

            self.last_day_price = await self.fetch_last_day_price(contract_id)
            await asyncio.sleep(0.5)


    async def fetch_last_day_price(self, contract_id):
        """
        Fetch the latest last-day price from the IBKR API.
        """
        try:
            last_day_price = self.ibkr.last_day_price(contract_id)
            return last_day_price.get('last_day_price')
        except Exception as e:
            print(f"Error fetching last day price: {e}")

        return None

    async def update_live_data(self):
        """
        Periodically update live data for current strikes.
        """
        while self.keep_running:
            if self.strike_data_list:
                for strike_entry in self.strike_data_list:
                    for option_type in ["call", "put"]:
                        option_data = strike_entry.get(option_type)
                        if option_data and option_data.get("conid"):
                            live_data = await self.fetch_live_data(option_data["conid"])
                            option_data["live_data"] = live_data if live_data else []
                            await self.send(
                                text_data=json.dumps(
                                    {"option_chain_data": self.strike_data_list, "error": None, "authentication": True}
                                )
                            )
                            await asyncio.sleep(0.1)
            await asyncio.sleep(0.2)

    @database_sync_to_async
    def get_user_from_token(self, user_id):
        """
            Return the authenticated user.
        """
        try:
            return CustomUser.objects.get(id=user_id)
        except Exception:
            return AnonymousUser()

    @database_sync_to_async
    def get_contract_month(self, contract_id):
        try:
            system_obj = SystemData.objects.get(contract_id=contract_id, created_at__date=now().date(),
                                                user=self.userObj)
            if system_obj:
                return system_obj.contract_month
            else:
                return None
        except SystemData.DoesNotExist:
            return None
