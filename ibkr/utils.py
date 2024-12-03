import time


from ibapi.contract import Contract
from ib_insync import IB

from ibkr.mixins import IBClient


def request_account_summary():
    client = IBClient('127.0.0.1', 7496, 5777)
    time.sleep(1)  # Wait for the connection to be established
    account_summary_tags = ",".join([
        "AccountType", "NetLiquidation", "TotalCashValue", "SettledCash", "AccruedCash", "BuyingPower",
        "EquityWithLoanValue", "PreviousEquityWithLoanValue", "GrossPositionValue", "RegTEquity", "RegTMargin",
        "SMA", "InitMarginReq", "MaintMarginReq", "AvailableFunds", "ExcessLiquidity", "Cushion",
        "FullInitMarginReq", "FullMaintMarginReq", "FullAvailableFunds", "FullExcessLiquidity",
        "LookAheadNextChange", "LookAheadInitMarginReq", "LookAheadMaintMarginReq", "LookAheadAvailableFunds",
        "LookAheadExcessLiquidity", "HighestSeverity", "DayTradesRemaining", "Leverage", "$LEDGER",
        "$LEDGER:CURRENCY", "$LEDGER:ALL"
    ])
    client.reqAccountSummary(9001, "All", account_summary_tags)
    client.data_event.wait(5)  # Wait for the data to be received or timeout after 5 seconds
    client.disconnect()
    return {"account_summary": client.account_summary_data}


def request_historical_data(symbol: str):
    client = IBClient('127.0.0.1', 7496, 5777)
    time.sleep(1)  # Wait for the connection to be established

    contract = Contract()
    contract.symbol = symbol
    contract.secType = 'STK'
    contract.exchange = 'SMART'
    contract.currency = 'USD'
    what_to_show = 'TRADES'

    client.reqHistoricalData(
        2, contract, '', '30 D', '5 mins', what_to_show, True, 2, False, []
    )

    time.sleep(5)  # Wait for the data to be received
    client.disconnect()

# def get_market_data(con_id, exchange='SMART'):
#     # Connect to TWS API
#     ib = IB()
#     ib.connect('127.0.0.1', 7496, clientId=5777)  # Use 7496 for paper trading
#
#     # Define the contract using ConId
#     contract = Contract(conId=con_id, exchange=exchange)
#
#     # Request market data for the contract
#     ib.qualifyContracts(contract)
#     market_data = ib.reqMktData(contract)
#
#     # Wait for the data to load
#     ib.sleep(2)  # Allow time for the data to populate
#
#     # Disconnect when done
#     ib.disconnect()
#
#     return market_data