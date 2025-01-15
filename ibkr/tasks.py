import json
from datetime import timedelta, datetime

import requests


from celery import shared_task
from django.conf import settings
from django.utils.timezone import now
from django_celery_beat.models import PeriodicTask

from accounts.models import CustomUser
from core.celery_response import log_task_status
from core.exceptions import IBKRValueError, IBKRAppError
from core.views import IBKRBase
from ibkr.models import OnBoardingProcess, TimerData, Strikes
from ibkr.utils import calculate_strike_range_and_save, save_order, generate_customer_order_id


@shared_task(bind=True, name="")
def tickle_ibkr_session(self, data=None):
    """
    Task to hit the IBKR tickle API every 2 minutes to maintain the session.
    """
    task_name = "tickle_ibkr_session"
    onboarding_id = data.get('onboarding_id')
    user_id = data.get('user_id')
    task_id = data.get('task_id')

    onboarding_obj = OnBoardingProcess.objects.filter(id=onboarding_id, user_id=user_id).first()
    if not onboarding_obj:
        log_task_status(task_name, message="Onboarding instance not found.", additional_data={"onboarding_id": onboarding_id})


    ibkr = IBKRBase()
    response = ibkr.auth_status()
    if not response.get('success'):
        return _disable_task_and_update_status(onboarding_obj, task_id, task_name)
    elif response.get('success') and not response.get('data').get('authenticated'):
        return _disable_task_and_update_status(onboarding_obj, task_id, task_name)


    tickle_url = f"{settings.IBKR_BASE_URL}/tickle"

    try:
        tickle_response = requests.post(tickle_url, verify=False)
        if tickle_response.status_code != 200:
            return _disable_task_and_update_status(onboarding_obj, task_id, task_name)
    except requests.exceptions.RequestException as e:
        error_details = log_task_status(task_name, exception=e, additional_data={"payload": data})
        self.update_state(state="FAILURE", meta=error_details)
        raise

@shared_task(bind=True)
def update_timer(self, timer_id, task_id):
    task_name = "update_timer"
    try:
        # Perform the task logic
        timer = TimerData.objects.get(id=timer_id)
        if timer.timer_value > 0:
            timer_value = timer.timer_value
            if isinstance(timer_value, str):
                timer_value = int(timer_value)
            timer_value -= 1
            timer.timer_value = timer_value

            # increase time by 1 minute
            timer_start_time = timer.start_time
            current_datetime = datetime.combine(datetime.today(), timer_start_time)
            updated_datetime = current_datetime + timedelta(minutes=1)
            timer.start_time = updated_datetime.time()
            timer.place_order = "P" if timer_value != 0 else "N"
            timer.save()
            success_details = log_task_status(task_name, message="Timer updated successfully", additional_data={"timer_id": timer_id})
        else:
            task = PeriodicTask.objects.filter(id=task_id).first()
            task.enabled = False
            task.save()
            success_details = log_task_status(task_name, message="Timer completed", additional_data={"timer_id": timer_id})
        self.update_state(state="SUCCESS", meta=success_details)

    except Exception as e:
        error_details = log_task_status(task_name, exception=e, additional_data={"timer_id": timer_id})
        self.update_state(state="FAILURE", meta=error_details)
        raise


@shared_task(bind=True)
def fetch_and_save_strikes(self, contract_id, user_id, month, task_date, task_id):
    task_name = "fetch_and_save_strikes"
    today = now().date()
    if str(today) != task_date:
        # Disable the task if the date doesn't match
        Strikes.objects.filter(contract_id=contract_id, user_id=user_id).delete()

        task = PeriodicTask.objects.filter(id=task_id).first()
        if task:
            task.enabled = False
            task.save()
        success_details = log_task_status(task_name, message="Task disabled as it is completed for today",
                                          additional_data={"task_id": task_id})
        self.update_state(state="SUCCESS", meta=success_details)
        return
    ibkr = IBKRBase()
    strikes_response = ibkr.fetch_strikes(contract_id, month)
    if strikes_response.get('success'):
        # fetch the last day price of the contract
        last_day_price = ibkr.last_day_price(contract_id)
        if last_day_price.get('success'):
            try:
                calculate_strike_range_and_save(strikes_response.get("data"), last_day_price.get('last_day_price'), contract_id, month, user_id, ibkr)
            except IBKRValueError as e:
                error_details = log_task_status(task_name, exception=e, additional_data={"contract_id": contract_id})
                self.update_state(state="FAILURE", meta=error_details)
                raise
    else:
        error_details = log_task_status(task_name, message="Unable to authenticate with IBKR Api. Please login first to continue", additional_data={"contract_id": contract_id})
        self.update_state(state="FAILURE", meta=error_details)
        raise

    success_details = log_task_status(task_name, message="Strikes fetched and saved", additional_data={"contract_id": contract_id})
    self.update_state(state="SUCCESS", meta=success_details)


@shared_task(bind=True)
def place_orders_task(self, user_id, data):
    task_name = "place_orders_task"
    data = json.loads(data)
    ibkr = IBKRBase()
    account_data = ibkr.brokerage_accounts()
    account = None
    if account_data.get('success'):
        accounts = account_data.get('data', {}).get("accounts")

        if accounts:
            # Fetch the first ID of the account
            account = accounts[0]

    user_obj = CustomUser.objects.filter(id=user_id).first()
    timer_obj = TimerData.objects.filter(user=user_obj, created_at__date=now().date()).first()
    save_order_data = {"user": user_obj, "accountId": account}

    for obj in data:
        # Place Sell Order
        customer_order_id = generate_customer_order_id()
        sell_order_data = {"orders": [{
                "acctId": account,
                "conid": obj.get('conid'),
                "manualIndicator": True,
                "orderType": "LMT",
                "price": obj.get("limit_sell") * obj.get('quantity'),
                "side": "SELL",
                "tif": "DAY",
                "quantity": obj.get('quantity'),
                "cOID": customer_order_id
            }]
        }
        print(sell_order_data)
        print("#1" * 10)
        sell_order_response = ibkr.placeOrder(account, sell_order_data)
        if not handle_order_response(self, task_name, ibkr, sell_order_response, obj, save_order_data, "SELL", customer_order_id):
            return

        timer_obj.place_order = "D"
        timer_obj.save()

        # Place Stop Loss Buy Order
        customer_order_id = generate_customer_order_id()
        stop_loss_price = obj.get("price") + obj.get("price") * (obj.get("stop_loss") / 100)
        stop_loss_order_data = sell_order_data.copy()
        stop_loss_order_data["orders"][0].update({
            "price": round(stop_loss_price, 2) * obj.get('quantity'),
            "side": "BUY",
            "orderType": "STP",
            "cOID": customer_order_id
        })

        stop_loss_response = ibkr.placeOrder(account, stop_loss_order_data)
        if not handle_order_response(self, task_name, ibkr, stop_loss_response, obj, save_order_data, "BUY", customer_order_id,
                                     stop_loss=True):

            return

        # Place Take Profit Buy Order
        customer_order_id = generate_customer_order_id()

        take_profit_price = obj.get('price')/100 * obj.get("take_profit")
        take_profit_order_data = sell_order_data.copy()
        take_profit_order_data["orders"][0].update({
            "price": round(take_profit_price, 2) * obj.get('quantity'),
            "side": "BUY",
            "orderType": "LMT",
            "cOID": customer_order_id
        })
        print(take_profit_order_data)
        print("#3" * 10)
        take_profit_response = ibkr.placeOrder(account, take_profit_order_data)
        if not handle_order_response(self, task_name, ibkr, take_profit_response, obj, save_order_data, "BUY", customer_order_id,
                                     take_profit=True):

            return


    success_details = log_task_status(task_name, message="Order Placed and saved in db.")
    self.update_state(state="SUCCESS", meta=success_details)


def handle_order_response(self, task_name, ibkr, order_response, obj, save_order_data, side, customer_order_id, stop_loss=False,
                          take_profit=False):
    """
    Handles order API response, saves the order data, and confirms order if needed.
    """

    if order_response.get("success"):
        response = None
        error = None
        data =  order_response.get("data")
        print(data)
        print("$" * 100)
        print(type(data))
        if isinstance(data, list):
            order_id = order_response.get("data", [])[0].get("order_id")
            reply_id = order_response.get("data", [])[0].get("id")
            print(reply_id)
            print("#" * 100)
            response = order_response
            while reply_id:
                # Attempt to confirm the order
                confirm_response = ibkr.replyOrder(reply_id, {"confirmed": True})
                print(confirm_response, "=====================")
                if not confirm_response.get("success"):
                    error_details = log_task_status(
                        task_name,
                        message=f"Failed to confirm order reply for {side} order.",
                        additional_data={"replyId": reply_id}
                    )
                    self.update_state(state="FAILURE", meta=error_details)
                    return False

                # Check if the order_id is present after confirmation
                order_confirmed_id = confirm_response.get("data", {})[0].get("order_id")
                if order_confirmed_id:
                    reply_id = None
                    response = confirm_response
                    break  # Order confirmed, exit loop

                reply_id = confirm_response.get("data", {})[0].get("id")
        else:
            error = data.get("error")


        # Save the order data
        save_order_data.update({
            'conid': obj.get('conid'),
            'optionType': obj.get('optionType'),
            'orderType': 'STP' if stop_loss else 'LMT',
            'price': obj.get("price"),
            'side': side,
            'tif': 'DAY',
            'quantity': obj.get('quantity'),
            'limit_sell': obj.get('limit_sell', ''),
            'stop_loss': obj.get('stop_loss', ''),
            'take_profit': obj.get('take_profit', ''),
            'order_api_response': response if not error else error,
            'customer_order_id': customer_order_id
        })
        try:
            save_order(save_order_data)
        except IBKRAppError as e:
            error_details = log_task_status(
                task_name,
                exception=e,
                message="Unable to save order",
                additional_data={"orderType": side}
            )
            self.update_state(state="FAILURE", meta=error_details)
            return False
    else:
        error_details = log_task_status(
            task_name,
            message=f"Failed to place {side} order.",
            additional_data={"orderType": side}
        )
        self.update_state(state="FAILURE", meta=error_details)
        return False

    return True


def _disable_task_and_update_status(onboarding_obj, task_id, task_name):
    """
    Helper function to disable a task and update onboarding status.
    """
    onboarding_obj.authenticated = False
    onboarding_obj.save()

    task = PeriodicTask.objects.filter(id=task_id).first()
    if task:
        task.enabled = False
        task.save()

    return log_task_status(task_name, message="Authentication failed. Task disabled.", additional_data={"onboarding_id": task_id})
