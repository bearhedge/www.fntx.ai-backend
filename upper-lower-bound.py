import yfinance as yf
import requests

def get_yahoo_options(ticker, expiration_date):
    """Fetch options data from Yahoo Finance for a given ticker and expiration date."""
    try:
        stock = yf.Ticker(ticker)
        print(stock.options, "==============")
        expirations = stock.options
        if expiration_date not in expirations:
            raise ValueError(f"Expiration date {expiration_date} not available. Available dates: {expirations}")

        options_chain = stock.option_chain(expiration_date)
        print(options_chain)
        print("option_chain" * 100)
        return options_chain
    except Exception as e:
        print(f"Error fetching options from Yahoo Finance: {e}")
        return None

# Step 2: Extract Target Option Contract Symbol
def extract_contract_symbol(options_chain, strike, option_type):
    """Extract the contract symbol for a specific strike price and option type."""
    options = options_chain.calls if option_type.upper() == "C" else options_chain.puts
    target_option = options[options['strike'] == strike]

    if target_option.empty:
        raise ValueError(f"No {option_type} option found for strike {strike}.")

    return target_option.iloc[0]['contractSymbol']

# Step 3: Map Yahoo Finance Contract Symbol to IBKR Conid
def get_ibkr_conid(base_url, ticker, expiration, strike, right):
    """Map Yahoo contract to IBKR conid."""
    url = f"{base_url}/iserver/secdef/search?symbol={ticker}"
    response = requests.get(url, verify=False)
    if response.status_code != 200:
        raise ConnectionError(f"Failed to fetch IBKR contracts: {response.status_code}, {response.text}")

    contracts = response.json()
    print(contracts, "----------------------")
    target_contract = next(
        (c for c in contracts if c.get('expiry') == expiration and c.get('strike') == strike and c.get('right') == right),
        None
    )

    if not target_contract:
        raise ValueError("Target option not found in IBKR contracts.")

    return target_contract['conid']

# Step 4: Query IBKR for Live Data
def get_ibkr_live_data(base_url, conid):
    """Fetch real-time data for a given conid from IBKR."""
    url = f"{base_url}/iserver/marketdata/snapshot?conids={conid}"
    response = requests.get(url)
    if response.status_code != 200:
        raise ConnectionError(f"Failed to fetch IBKR live data: {response.status_code}, {response.text}")

    return response.json()

# Test the Workflow
def main():
    ticker = "SPY"
    expiration_date = "2024-12-20"
    strike_price = 470
    option_type = "C"

    # IBKR API Base URL (replace with actual base URL)
    ibkr_base_url = "https://localhost:5000/v1/api"

    try:
        # Step 1: Fetch Yahoo Finance Options Data
        options_chain = get_yahoo_options(ticker, expiration_date)
        if not options_chain:
            return

        # Step 2: Extract Contract Symbol
        contract_symbol = extract_contract_symbol(options_chain, strike_price, option_type)
        print(f"Yahoo Finance Contract Symbol: {contract_symbol}")

        # Step 3: Map to IBKR Conid
        conid = get_ibkr_conid(ibkr_base_url, ticker, expiration_date, strike_price, option_type)
        print(f"IBKR Conid: {conid}")

        # Step 4: Fetch Live Data from IBKR
        live_data = get_ibkr_live_data(ibkr_base_url, conid)
        print("IBKR Live Data:", live_data)

    except Exception as e:
        print(f"Error in workflow: {e}")

if __name__ == "__main__":
    main()