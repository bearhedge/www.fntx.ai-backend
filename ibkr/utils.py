# import time
# import pandas as pd
# import numpy as np
import json


def fetch_bounds_from_json(json_data):
    highest_prices = [entry['h'] for entry in json_data['data']]
    lowest_prices = [entry['l'] for entry in json_data['data']]

    max_highest_price = max(highest_prices)
    min_lowest_price = min(lowest_prices)

    response = {
        "upper_bound": max_highest_price,
        "Lower_bound": min_lowest_price
    }

    return response

# def compute_returns(prices):
#     returns = prices.pct_change().dropna()
#     return returns
#
# def calculate_statistics(returns):
#     mean_return = returns.mean()
#     std_dev_return = returns.std()
#     return mean_return, std_dev_return
#
# def annualize_volatility(daily_std_dev):
#     annualized_volatility = daily_std_dev * np.sqrt(252)
#     return annualized_volatility
#
# def compute_expected_range(latest_price, daily_volatility):
#     range_upper = latest_price * (1 + daily_volatility)
#     range_lower = latest_price * (1 - daily_volatility)
#     return range_upper, range_lower

