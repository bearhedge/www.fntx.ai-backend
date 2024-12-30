from core.exceptions import IBKRValueError


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
    print(all_call_strikes, all_put_strikes)
    call_strikes = [strike for strike in all_call_strikes if lower_bound <= strike <= upper_bound]
    put_strikes = [strike for strike in all_put_strikes if lower_bound <= strike <= upper_bound]

    data['call'] = call_strikes
    data['put'] = put_strikes
    return data




