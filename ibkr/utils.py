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
    data = {}
    if not last_day_price:
        raise IBKRValueError("Last day price is required to calculate strike ranges.")

    # Calculate the ±5% range
    lower_bound = last_day_price * 0.95
    upper_bound = last_day_price * 1.05

    all_call_strikes = strikes_response.get('call')
    all_put_strikes = strikes_response.get('put')
    call_strikes = [strike for strike in all_call_strikes if lower_bound <= strike <= upper_bound]
    put_strikes = [strike for strike in all_put_strikes if lower_bound <= strike <= upper_bound]

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
    Format: FNTX-live-order-001
    """
    last_order = PlaceOrder.objects.aggregate(
        max_id=Max('customer_order_id')
    )['max_id']

    if last_order:
        # Extract numeric part and increment
        prefix, order_num = last_order.split('-live-orders-')
        next_order_num = int(order_num) + 1
        new_order_id = f"{prefix}-live-order-{next_order_num}"
    else:
        new_order_id = "FNTX-live-orders-1"

    return new_order_id


