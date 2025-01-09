import datetime
import re
from django.db.models import Max

from core.exceptions import IBKRValueError
from ibkr.models import PlaceOrder


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


def calculate_strike_range(strikes_response, last_day_price):
    """
    Calculate the strike range for call and put options based on the last price.

    :param strikes_response: Dictionary containing call and put strike prices.
    :param last_day_price: The last day price of the asset.
    :return: Dictionary containing filtered call and put strike ranges.
    """
    range_count = 15
    data = {}
    if not last_day_price:
        raise IBKRValueError("Last day price is required to calculate strike ranges.")


    all_call_strikes = strikes_response.get('call')
    all_put_strikes = strikes_response.get('put')

    call_strikes = [strike for strike in all_call_strikes if strike <= last_day_price][:range_count]

    # Filter for put strikes (greater than or equal to last price)
    put_strikes = [strike for strike in all_put_strikes if strike >= last_day_price][-range_count:]

    data['call'] = call_strikes
    data['put'] = put_strikes
    return data


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

    last_order = PlaceOrder.objects.aggregate(
        max_id=Max('customer_order_id')
    )['max_id']

    if last_order:


        match = re.search(r"^(.*?)-id-(\d+)$", last_order)
        if match:
            prefix, order_num = match.groups()
            next_order_num = int(order_num) + 1
            new_order_id = f"{prefix}-id-{next_order_num}"
        else:
            raise ValueError("Invalid customer_order_id format in database.")
    else:
        new_order_id = "order-id-1"

    return new_order_id
