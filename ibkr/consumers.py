import asyncio
import json

from channels.db import database_sync_to_async
from django.utils.timezone import now
from asgiref.sync import sync_to_async

from core.base_consumer import BaseConsumer
from .models import TimerData, PlaceOrder
from .utils import transform_ibkr_data


class StrikesConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.send_place_order_task = None
        self.userObj = None
        self.fetch_strikes = None

    async def connect(self):
        await super().connect()

        self.send_place_order_task = asyncio.create_task(self.send_place_order_updates())

        # Start tasks for fetching last-day price and updating live data
        self.update_last_price_task = asyncio.create_task(self.update_last_price_periodically())
        self.update_live_data_task = asyncio.create_task(self.update_live_data())

    async def disconnect(self, code):
        self.keep_running = False

        if self.send_place_order_task:
            self.send_place_order_task.cancel()

        if self.fetch_strikes:
            self.fetch_strikes.cancel()

        await super().disconnect(code)


    async def receive(self, text_data):
        data = json.loads(text_data)
        contract_id = data.get("contract_id")
        if not contract_id:
            await self.send(text_data=json.dumps({"error": "contract_id is a required parameter.", "authentication": True}))
            return

        self.month = await self.get_contract_month(contract_id)
        self.scope["contract_id"] = contract_id
        self.fetch_strikes = asyncio.create_task(self.fetch_and_validate_strikes(contract_id))

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

            await asyncio.sleep(1)

    @sync_to_async
    def fetch_timer_data(self):
        # This method runs in a synchronous thread to avoid async ORM conflicts
        return list(TimerData.objects.filter(user=self.userObj, created_at__date=now().date()))


class TradeManagementConsumer(BaseConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.placed_orders_status = None
        self.orders = None
        self.Pnl_tasks = []
        self.orders_list = []


    async def connect(self):
        await super().connect()

        self.orders = await self.fetch_today_orders()
        self.placed_orders_status = asyncio.create_task(self.orders_status())

    async def disconnect(self, code):
        self.keep_running = False

        if self.placed_orders_status:
            self.placed_orders_status.cancel()

        if self.Pnl_tasks:
            for task in self.Pnl_tasks:
                task.cancel()

        await super().disconnect(code)

    async def orders_status(self):
        try:
            while self.keep_running:
                if not self.orders:
                    await asyncio.sleep(0.1)
                    continue

                for order in self.orders:
                    if order.order_status == "Filled" and not any(task.get_name() == str(order.id) for task in self.Pnl_tasks):
                        task = asyncio.create_task(self.calculate_pnl(order))
                        task.set_name(str(order.id))
                        self.Pnl_tasks.append(task)
                    order_id = None
                    order_status = ""

                    order_payload = order.order_api_response
                    if not order_payload:
                        order_status = "Cancelled"
                    elif order_payload.get('error'):
                        order_status = "Cancelled"
                    elif order_payload.get('cqe', {}).get('rejections', ''):
                        order_status = "Cancelled"
                    else:
                        order_id = order_payload.get('order_id')
                    if order_id:
                        response = self.ibkr.orderStatus(order_id)
                        if not response.get('success'):
                            order_status = ""
                        else:
                            order_status = response.get('data').get('order_status')
                            average_price = response.get('data').get('average_price')
                            order.order_status = order_status
                            order.average_price = average_price if average_price else 0.0
                            await database_sync_to_async(order.save)()

                    found = False
                    for order_item in self.orders_list:
                        if str(order.id) in order_item:
                            order_item[str(order.id)] = order_status
                            found = True
                            break

                    if not found:
                        self.orders_list.append({str(order.id): order_status})



                    # Send the updated data immediately
                    await self.send(text_data=json.dumps(self.orders_list))
                    await asyncio.sleep(0)

                await asyncio.sleep(2)
        except Exception as e:
            print(e.args)

    async def calculate_pnl(self, order):
        while self.keep_running:
            entry_price = await self.fetch_last_day_price(order.conid)
            sold_price = order.average_price
            quantity = order.quantity

            if entry_price is None or sold_price is None:
                return

            # Calculate Realized P&L (Profit or Loss)
            pnl = (sold_price - entry_price) * quantity

            pnl_data = {
                'contract': order.con_desc2,
                'volume': order.quantity,
                'sold_price': sold_price,
                'current_price': entry_price,
                'pnl': pnl,
                'order_id': order.id,
            }

            await self.send(text_data=json.dumps(pnl_data))
            await asyncio.sleep(1.5)

    @sync_to_async
    def fetch_today_orders(self):
        # This method runs in a synchronous thread to avoid async ORM conflicts
        date = now().date()
        return list(PlaceOrder.objects.filter(user=self.userObj, created_at__date=date))


class ChartsData(BaseConsumer):
    def __init__(self, *args, **kwargs):
        self.stream_data = []
        self.contract_id = None
        self.month = None
        self.candle_graph_task = None
        self.prices_task = None
        self.close_price = None
        self.pre_market_price = None
        self.keep_running = True
        super().__init__(*args, **kwargs)

    async def connect(self):
        await super().connect()

    async def disconnect(self, code):
        self.keep_running = False

        if self.candle_graph_task and not self.candle_graph_task.done():
            self.candle_graph_task.cancel()
        if self.prices_task and not self.prices_task.done():
            self.prices_task.cancel()

        await super().disconnect(code)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            ticker = data.get("ticker")
            authentication = self.ibkr.auth_status()
            if not authentication.get("success"):
                await self.send(text_data=json.dumps({"authentication": False, "error": "You are not authenticated with IBKR. Please login first."}))
                await self.close()
                return
            if not ticker:
                await self.send(text_data=json.dumps({"error": "ticker is a required parameter.", "authentication": True}))
                await self.close()
                return

            self.contract_id, self.month = await self.ticker_contract(ticker)
            if not self.contract_id:
                await self.send(text_data=json.dumps({"error": f"Unable to select contract for the selected ticker {ticker}"}))
                await self.close()
                return
            self.candle_graph_task = asyncio.create_task(self.candle_data())
            self.prices_task = asyncio.create_task(self.updated_prices())
        except Exception as e:
            print(e.args)


    async def updated_prices(self):
        while self.keep_running:
            if not self.contract_id:
                await asyncio.sleep(0.2)
                continue
            live_data_response = self.ibkr.last_day_price(self.contract_id)
            if live_data_response.get('success'):
                self.pre_market_price = live_data_response.get('last_day_price')
                await self.send(text_data=json.dumps({'pre_market_price': self.pre_market_price}))
                await asyncio.sleep(1)


    async def candle_data(self):
        while self.keep_running:
            if not self.contract_id:
                await asyncio.sleep(0.1)
                continue
            print("-------------------------found contract--------------------------")
            history_data = self.ibkr.historical_data(self.contract_id, '1min', '5min')
            print(history_data, "=====================")
            if history_data.get('success'):
                try:
                    formatted_data = transform_ibkr_data(history_data.get('data'), self.contract_id)
                except Exception as e:
                    print(e.args)
                await self.send(text_data=json.dumps(formatted_data))
                await asyncio.sleep(0)
            else:
                await self.send(text_data=json.dumps({"conId": self.contract_id}))
                await asyncio.sleep(0)


            await asyncio.sleep(2)


class StreamOptionData(BaseConsumer):
    def __init__(self, *args, **kwargs):
        self.contract_id = None
        self.fetch_strikes_task = None
        self.live_data_task = None
        self.all_strikes = {}
        self.keep_running = True
        super().__init__(*args, **kwargs)

    async def connect(self):
        await super().connect()

        # Start tasks for fetching last-day price and updating live data
        self.update_last_price_task = asyncio.create_task(self.update_last_price_periodically())
        self.update_live_data_task = asyncio.create_task(self.update_live_data())

    async def disconnect(self, code):
        self.keep_running = False

        if self.fetch_strikes_task:
            self.fetch_strikes_task.cancel()

        await super().disconnect(code)

    async def receive(self, text_data):
        # Parse received JSON data
        data = json.loads(text_data)
        ticker = data.get("ticker")
        authentication = self.ibkr.auth_status()
        if not authentication.get("success"):
            await self.send(text_data=json.dumps({"authentication": False, "error": "You are not authenticated with IBKR. Please login first."}))
            await self.close()
            return
        if not ticker:
            await self.send(text_data=json.dumps({"error": "ticker is a required parameter.", "authentication": True}))
            await self.close()
            return

        self.contract_id, self.month = await self.ticker_contract(ticker)
        if not self.contract_id:
            await self.send(text_data=json.dumps({"error": f"Unable to select contract for the selected ticker {ticker}"}))
            await self.close()
            return
        self.scope["contract_id"] = self.contract_id

        self.fetch_strikes_task = asyncio.create_task(self.fetch_and_validate_strikes(self.contract_id))
