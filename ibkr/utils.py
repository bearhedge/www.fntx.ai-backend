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
