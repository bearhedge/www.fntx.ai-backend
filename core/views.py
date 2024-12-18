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

    def tickle(self):
        try:
            response = requests.get(f"{self.ibkr_base_url}/tickle", verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}

    def placeOrder(self, order_data):
        try:
            url = f"{self.ibkr_base_url}/iserver/account/{order_data['accountId']}/orders"
            response = requests.post(url, json=[order_data], verify=False)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "status": response.status_code}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "status": 500}



