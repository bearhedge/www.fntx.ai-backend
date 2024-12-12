import requests
from django.conf import settings
from django.db import models

from accounts.models import CustomUser
from core.models import BaseModel


class OnBoardingProcess(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    authenticated = models.BooleanField(null=True)
    level_4_permission = models.BooleanField(null=True)
    active_subscription = models.BooleanField(null=True)
    metamask_address = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return self.user.email

class SystemData(BaseModel):
    CONTRACT_TYPE_CHOICES = [
        ('call', 'Call'),
        ('put', 'Put'),
        ('both', 'Both'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    instrument = models.CharField(max_length=100)
    analysis_time = models.IntegerField()
    time_frame = models.CharField(max_length=100)
    time_steps = models.IntegerField()
    confidence_level = models.IntegerField()
    contract_expiry = models.IntegerField()
    contract_id = models.CharField(max_length=100)
    no_of_contracts = models.IntegerField()
    contract_type = models.CharField(max_length=4, choices=CONTRACT_TYPE_CHOICES)

    def __str__(self):
        return f"{self.user.email} - {self.instrument}"

    def get_available_margin(self):
        try:
            ibkr_base_url = settings.IBKR_BASE_URL
            account_id = "U15796707"  # Replace with dynamic account ID if needed
            response = requests.get(f"{ibkr_base_url}/portfolio/{account_id}/summary", verify=False)
            if response.status_code == 200:
                account_summary = response.json()
                available_margin = account_summary.get('available_margin', 0)
                return available_margin
            else:
                return 0
        except Exception as e:
            return 0

    def calculate_order_amount(self):
        available_margin = self.get_available_margin()
        order_amount = available_margin * (self.confidence_level / 100)
        return order_amount

class OrderData(SystemData):
    limit_sell = models.FloatField()
    limit_buy = models.FloatField()
    stop_loss = models.FloatField()
    take_profit = models.FloatField()

    def __str__(self):
        return f"{self.user.email} - {self.instrument}"

class TradingStatus(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    status = models.CharField(max_length=1, blank=True, null=True)
    wait_time = models.IntegerField()

    def __str__(self):
        return f"{self.user.email} - {self.status} - {self.wait_time} minutes"

class Instrument(BaseModel):
    INSTRUMENT_TYPE_CHOICES = [
        ('EQUITY', 'equity'),
        ('COMMODITY', 'commodity'),
        ('CRYPTO', 'crypto'),
    ]
    instrument = models.CharField(max_length=100)
    instrument_type = models.CharField(max_length=100, choices=INSTRUMENT_TYPE_CHOICES)
    conid = models.IntegerField()
    exchange = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.instrument}"


