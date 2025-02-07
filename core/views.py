import json
import re
import time

import requests
from django.conf import settings


class IBKRBase:
    def __init__(self):
        self.ibkr_base_url = settings.IBKR_BASE_URL

    def auth_status(self):
        try:
            response = requests.post(f"{self.ibkr_base_url}/iserver/auth/status", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": "Unable to authenticate with IBKR API. Please login on client portal.", "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": "Unable to authenticate with IBKR API", "status": 500}


    def reauthenticate(self):
        """
        Handles reauthentication with the IBKR API.
        """
        try:
            response = requests.post(f"{self.ibkr_base_url}/iserver/reauthenticate", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}

    def brokerage_accounts(self):
        """
        Get list of all the accounts of the user
        """
        try:
            response = requests.get(f"{self.ibkr_base_url}/iserver/accounts", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": "Unable to authenticate with IBKR API. Please login on client portal.", "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": "Unable to authenticate with IBKR API", "status": 500}


    def account_summary(self):
        acc_response = self.brokerage_accounts()
        if acc_response.get('success'):
            accounts = acc_response.get('data', {}).get('accounts')
            if accounts:
                account = accounts[0]
        else:
            return {"success": False, "error": acc_response.get("error"),
                    "status": acc_response.get("status")}

        try:
            request_url = f"{self.ibkr_base_url}/portfolio/accounts"
            requests.get(url=request_url, verify=False)
            time.sleep(0.5)
            response = requests.get(f"{self.ibkr_base_url}/portfolio/{account}/summary", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False,
                        "error": "Unable to authenticate with IBKR API. Please login on client portal.",
                        "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": "Unable to authenticate with IBKR API", "status": 500}

    def get_spy_conId(self, symbol):
        """
        Fetch the data for a particular symbol
        """
        try:
            response = requests.get(f"{self.ibkr_base_url}/iserver/secdef/search?symbol={symbol}", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


    def fetch_strikes(self, contract_id, month):
        try:
            response = requests.get(f"{self.ibkr_base_url}/iserver/secdef/strikes?conid={contract_id}&sectype=OPT&month={month}", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e), "status": 500}


    def tickle(self):
        try:
            response = requests.post(f"{self.ibkr_base_url}/tickle", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}

    def historical_data(self, conId, bar, period=None):
        if not period:
            period = "1w"
        try:
            response = requests.get(f"{self.ibkr_base_url}/iserver/marketdata/history?conid={conId}&period={period}&bar={bar},", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code, "error": response.content}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}


    def placeOrder(self, account, order_data):
        try:
            url = f"{self.ibkr_base_url}/iserver/account/{account}/orders"
            response = requests.post(url, json=order_data, verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}

    def replyOrder(self, reply_id, json_content):
        try:
            url = f"{self.ibkr_base_url}/iserver/reply/{reply_id}"
            response = requests.post(url, json=json_content, verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code, "error": response.content}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}


    def orderStatus(self, order_id):
        try:
            url = f"{self.ibkr_base_url}/iserver/account/order/status/{order_id}"
            response = requests.get(url, verify=False)
            print(response.text)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code, "error": response.text}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}


    def cancelOrder(self, order_id, account_id):
        try:
            url = f"{self.ibkr_base_url}/iserver/account/{account_id}/order/{order_id}"
            response = requests.delete(url=url, verify=False)
            if response.status_code == 200:
                return {"success": True}
            else:
                return {"success": False, "status": response.status_code, "error": response.text}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}


    def modifyOrder(self, order_id, account_id, json_content):
        try:
            url = f"{self.ibkr_base_url}/iserver/account/{account_id}/order/{order_id}"
            response = requests.post(url=url, json=json_content, verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code, "error": response.text}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}


    def retrieveOrders(self):
        try:
            self.brokerage_accounts()
            url = f"{self.ibkr_base_url}/iserver/account/order/status/1533705195"
            response = requests.get(url, verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}



    def last_day_price(self, contract_id):
        try:
            requests.get(url=f"{self.ibkr_base_url}/iserver/marketdata/snapshot?conids={contract_id}&fields=31,7295,70", verify=False)
            # wait for one second to again hit the snapshot API
            time.sleep(1)

            response = requests.get(f"{self.ibkr_base_url}/iserver/marketdata/snapshot?conids={contract_id}&fields=31,7295,70", verify=False)
            if response.status_code == 200:
                data = response.json()
                if data:
                    price = data[0].get('31')
                    pre_market_price = data[0].get('7295')
                    data_type = data[0].get('6509')
                    if price:
                        pattern = r'\d+(\.\d+)?'
                        match = re.search(pattern, price)
                        last_day_price = match.group(0) if match else None
                        if last_day_price:
                            return {"success": True, "last_day_price": float(last_day_price), "pre_market_price": pre_market_price, "data_type": data_type}
                        else:
                            return {"success": False, "error": "Error fetching the last price for the given contract id.", "status":500}
                    else:
                        return {"success": False, "error": "Error fetching the last price for the given contract id.",
                                "status": 500}


            else:
                return {"success": False, "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}


    def strike_info(self, conid, strike, right, month):
        url = f'{self.ibkr_base_url}/iserver/secdef/info?conid={conid}&secType=OPT&month={month}&strike={strike}&right={right}'
        try:
            response = requests.get(url, verify=False)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return {"success": True, "data": data}
                else:
                    return {"success": False, "status": "No data"}
            else:
                return {"success": False, "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}
