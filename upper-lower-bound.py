import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

def fetch_trailing_prices(ticker, num_days):
    # Calculate the end date (today) and start date (double the required days to ensure enough data)
    end_date = datetime.today()
    start_date = end_date - timedelta(days=num_days * 2)  # Fetch extra days to account for non-trading days

    # Generate all business days (trading days) within the date range
    all_dates = pd.date_range(start=start_date, end=end_date, freq='B')  # 'B' stands for business day frequency

    # Fetch historical price data from Yahoo Finance
    data = yf.download(ticker, start=all_dates[0], end=all_dates[-1] + timedelta(days=1))  # Include end day

    # Check if any data was fetched
    if data.empty:
        raise ValueError("No data fetched for the specified date range.")

    # Convert the index to date-only format to align with generated trading days
    data.index = data.index.date
    all_dates = all_dates.date

    # Filter the data to include only rows that match trading days
    data = data.loc[data.index.intersection(all_dates)]

    # Extract the closing prices from the data
    closing_prices = data['Close']

    # Ensure exactly `num_days` of data is returned (trim excess)
    if len(closing_prices) > num_days:
        closing_prices = closing_prices.tail(num_days)

    return closing_prices

def compute_returns(prices):
    # Calculate daily percentage returns from the closing prices
    returns = prices.pct_change().dropna()  # Drop the first NaN value caused by pct_change
    return returns

def calculate_statistics(returns):
    # Calculate the mean and standard deviation of daily returns
    mean_return = returns.mean()
    std_dev_return = returns.std()
    return mean_return, std_dev_return

def annualize_volatility(daily_std_dev):
    # Annualize the daily volatility using the square root of trading days in a year (252)
    annualized_volatility = daily_std_dev * np.sqrt(252)
    return annualized_volatility

def compute_expected_range(latest_price, daily_volatility):
    # Calculate the expected price range based on the latest price and daily volatility
    range_upper = latest_price * (1 + daily_volatility)
    range_lower = latest_price * (1 - daily_volatility)
    return range_upper, range_lower

# Parameters
ticker = 'SPY'  # Ticker symbol for the stock/ETF to analyze
num_days = int(input("Enter number of trailing trading days: "))  # User input for number of days to analyze

# Fetch and process data
try:
    # Fetch historical closing prices for the specified ticker and time frame
    prices = fetch_trailing_prices(ticker, num_days)
    print(f"Closing prices for the trailing {num_days} trading days from today:")
    print(prices)

    # Compute daily returns from the fetched prices
    returns = compute_returns(prices)
    print("\nDaily Returns:")
    print(returns)

    # Calculate statistical metrics: mean and standard deviation of returns
    mean_return, std_dev_return = calculate_statistics(returns)
    print(f"\nMean of Daily Returns: {mean_return:.6f}")
    print(f"Standard Deviation of Daily Returns: {std_dev_return:.6f}")

    # Calculate the annualized volatility based on the standard deviation of daily returns
    annualized_volatility = annualize_volatility(std_dev_return)
    print(f"Annualized Volatility: {annualized_volatility:.6f}")

    # Get the most recent closing price from the data
    latest_price = prices.iloc[-1]

    # Compute the expected upper and lower bounds for the stock price
    range_upper, range_lower = compute_expected_range(latest_price, std_dev_return)
    print(f"\nExpected Price Range for the latest price ({latest_price:.2f}):")
    print(f"Upper Bound: {range_upper:.2f}")
    print(f"Lower Bound: {range_lower:.2f}")

except ValueError as e:
    # Handle cases where no data was fetched
    print(e)
