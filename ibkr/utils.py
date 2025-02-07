from datetime import datetime

from django.db.models import Max, IntegerField
from django.db.models.functions import Cast, Substr

from core.exceptions import IBKRValueError
from ibkr.models import PlaceOrder, Strikes


def fetch_bounds_from_json(json_data):
    highest_prices = [entry.get('h', 0) for entry in json_data.get('data', {})]
    lowest_prices = [entry.get('l', 0) for entry in json_data.get('data', {})]

    max_highest_price = max(highest_prices)
    min_lowest_price = min(lowest_prices)

    response = {
        "upper_bound": max_highest_price,
        "lower_bound": min_lowest_price
    }

    return response


def calculate_strike_range_and_save(strikes_response, last_day_price, contract_id, month, user_id, ibkr):
    """
    Calculate the strike range for call and put options based on the last price.

    :param strikes_response: Dictionary containing call and put strike prices.
    :param last_day_price: The last day price of the asset.
    :param contract_id: Contract id of the selected ticker.
    :param month: First month of the contract if for which trading can be done.
    :param user_id: Uuid of the login user.
    :param ibkr: Object of class IBKRBase
    :return: Dictionary containing filtered call and put strike ranges.
    """
    range_count = 20
    if not last_day_price:
        raise IBKRValueError("Last day price is required to calculate strike ranges.")


    all_call_strikes = strikes_response.get('call')
    all_put_strikes = strikes_response.get('put')
    call_strikes = [strike for strike in all_call_strikes if strike >= last_day_price][:range_count]
    put_strikes = [strike for strike in all_put_strikes if strike <= last_day_price][-range_count:]


    today_call_strikes = 0
    today_put_strikes = 0

    # validate call and put strikes
    for strike in call_strikes:
        strike_info = ibkr.strike_info(contract_id, strike, 'C', month)
        if not strike_info.get("success"):
            continue
        for obj in strike_info["data"]:
            maturity_date = obj.get("maturityDate")
            if maturity_date and int(maturity_date) == int(datetime.now().strftime("%Y%m%d")):
                Strikes.objects.update_or_create(
                    contract_id=contract_id,
                    user_id=user_id,
                    strike_price=strike,
                    right= "C",
                    month=month,
                    defaults={
                        'last_price': last_day_price,
                        'strike_info': obj,

                }
                )
        today_call_strikes += 1
        if today_call_strikes == 14:
            break

    for strike in put_strikes:
        strike_info = ibkr.strike_info(contract_id, strike, 'P', month)
        if not strike_info.get("success"):
            continue
        for obj in strike_info["data"]:
            maturity_date = obj.get("maturityDate")
            if maturity_date and int(maturity_date) == int(datetime.now().strftime("%Y%m%d")):
                Strikes.objects.update_or_create(
                    contract_id=contract_id,
                    user_id=user_id,
                    strike_price=strike,
                    right="P",
                    month=month,
                    defaults={
                        'last_price': last_day_price,
                        'strike_info': obj,

                }
                )
        today_put_strikes += 1
        if today_put_strikes == 14:
            break



def save_order(data_dict):
    """
     Save the order in local db placed by the user.

     :param data_dict: Dictionary containing data that needs to be saved
    """
    return PlaceOrder.objects.create(**data_dict)


def generate_customer_order_id():
    """
    Generates a new customer_order_id by incrementing the last saved ID in the database.
    Format: order-id-1, order-id-2, etc.
    """

    last_order = PlaceOrder.objects.annotate(
        numeric_id=Cast(Substr('customer_order_id', 10), IntegerField())
    ).aggregate(max_id=Max('numeric_id'))['max_id']

    if last_order:
        next_order_num = last_order + 1
        new_order_id = f"order-id-{next_order_num}"

    else:
        new_order_id = "order-id-1"

    return new_order_id

def transform_ibkr_data(api_response, conid=None):
    data = api_response.pop('data', [])
    transformed_data = []
    highest_closing_prices = [entry.get('c', 0) for entry in data]
    closing_price = max(highest_closing_prices)

    for index, bar in enumerate(data):
        timestamp_ms = bar["t"]
        timestamp_s = timestamp_ms / 1000
        utc_datetime = datetime.utcfromtimestamp(timestamp_s)
        iso_date = utc_datetime.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

        transformed_data.append({
            "date": iso_date,
            "open": round(bar["o"], 2),
            "high": round(bar["h"], 2),
            "low": round(bar["l"], 2),
            "close": round(bar["c"], 2),
            "volume": round(bar["v"] * api_response.get("volumeFactor", 1)),
            "split": "",
            "dividend": "",
            "absoluteChange": "",
            "percentChange": "",
            "idx": {
                "index": index,
                "level": 12,
                "date": iso_date
            }
        })
    api_response['data'] = transformed_data
    api_response['conId'] = conid
    api_response['at_Close'] = closing_price
    return api_response
