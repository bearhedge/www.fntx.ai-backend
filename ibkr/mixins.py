from threading import Thread, Event

from ibapi.client import EClient
from ibapi.wrapper import EWrapper


class IBClient(EWrapper, EClient):
    def __init__(self, host, port, client_id):
        EClient.__init__(self, self)
        self.account_summary_data = []
        self.data_event = Event()
        self.connect(host, port, client_id)
        thread = Thread(target=self.run)
        thread.start()

    def error(self, req_id, code, msg, misc):
        if code in [2104, 2106, 2158]:
            print(msg)
        else:
            print('Error {}: {}'.format(code, msg))

    def accountSummary(self, req_id: int, account: str, tag: str, value: str, currency: str):
        data = {
            "req_id": req_id,
            "account": account,
            "tag": tag,
            "value": value,
            "currency": currency
        }
        self.account_summary_data.append(data)
        print(data)

    def accountSummaryEnd(self, req_id: int):
        print("AccountSummaryEnd. ReqId:", req_id)
        self.data_event.set()