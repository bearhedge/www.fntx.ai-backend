import time
import pandas as pd


def fetch_trailing_prices_from_json(json_data):
    # Extract the closing prices from the JSON response
    prices = pd.Series([entry['close'] for entry in json_data['data']])
    return prices

def compute_returns(prices):
    returns = prices.pct_change().dropna()
    return returns

def calculate_statistics(returns):
    mean_return = returns.mean()
    std_dev_return = returns.std()
    return mean_return, std_dev_return

def annualize_volatility(daily_std_dev):
    annualized_volatility = daily_std_dev * np.sqrt(252)
    return annualized_volatility

def compute_expected_range(latest_price, daily_volatility):
    range_upper = latest_price * (1 + daily_volatility)
    range_lower = latest_price * (1 - daily_volatility)
    return range_upper, range_lower

# conid = "123456"
# period = "2d"
# bar = "1h"
# exchange = "NYSE"
# outside_rth = True