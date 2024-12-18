import requests
from django.conf import settings
from django.db import models
from django.db.models import ForeignKey
from django_celery_beat.models import PeriodicTask
from accounts.models import CustomUser
from core.models import BaseModel


class OnBoardingProcess(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    authenticated = models.BooleanField(null=True)
    level_4_permission = models.BooleanField(null=True)
    active_subscription = models.BooleanField(null=True)
    metamask_address = models.CharField(max_length=500, blank=True, null=True)
    periodic_task = models.ForeignKey(PeriodicTask, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return self.user.email

class Instrument(BaseModel):
    INSTRUMENT_TYPE_CHOICES = [
        ('EQUITY', 'equity'),
        ('COMMODITY', 'commodity'),
        ('CRYPTO', 'crypto'),
    ]
    instrument = models.CharField(max_length=100)
    instrument_type = models.CharField(max_length=100, choices=INSTRUMENT_TYPE_CHOICES)
    instrument_data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"{self.instrument}"

class SystemData(BaseModel):
    CONTRACT_TYPE_CHOICES = [
        ('call', 'Call'),
        ('put', 'Put'),
        ('both', 'Both'),
    ]
    TIME_FRAME_CHOICES = [
        ('1-day', '1d'),
        ('4-hours', '4h'),
        ('1-hour', '1h'),
        ('30-min', '30min'),
        ('15-min', '15min'),
        ('5-min', '5min'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    instrument = ForeignKey(Instrument, on_delete=models.CASCADE, blank=True, null=True)
    analysis_time = models.IntegerField(blank=True, null=True)
    time_frame = models.CharField(max_length=100, choices=TIME_FRAME_CHOICES, blank=True, null=True)
    time_steps = models.IntegerField(blank=True, null=True)
    confidence_level = models.IntegerField(blank=True, null=True)
    contract_expiry = models.IntegerField(blank=True, null=True)
    contract_id = models.CharField(max_length=100, blank=True, null=True)
    no_of_contracts = models.IntegerField(blank=True, null=True)
    contract_type = models.CharField(max_length=4, choices=CONTRACT_TYPE_CHOICES, blank=True, null=True)
    upper_bound = models.FloatField(blank=True, null=True)
    lower_bound = models.FloatField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.email} - {self.instrument}"

    def get_available_margin(self):
        try:
            ibkr_base_url = settings.IBKR_BASE_URL
            account_id = "U15796707"
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

class TradingStatus(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    status = models.CharField(max_length=1, blank=True, null=True)
    wait_time = models.IntegerField()

    def __str__(self):
        return f"{self.user.email} - {self.status} - {self.wait_time} minutes"


class TimerData(BaseModel):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    timer_value = models.IntegerField()
    start_time = models.TimeField()
    place_order = models.BooleanField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.timer_value}"


class PlaceOrder(BaseModel):
    ORDER_TYPE_CHOICES =[
        ('LMT', 'LMT'),
        ('MKT', 'MKT'),
    ]
    SIDE_CHOICES = [
        ('BUY', 'BUY'),
        ('SELL', 'SELL'),
    ]
    TIF_CHOICES = [
        ('DAY', 'DAY'), #Day
        ('GTC', 'GTC'), #Good-Til-Canceled
        ('OPG', 'OPG'), #market-on-open
        ('IOC', 'IOC'), #Immediate-or-Cancel
        ('GTD', 'GTD'), #Good-Til-Date
        ('FOK', 'FOK'), #Fill-or-Kill
        ('DTC', 'DTC'), #Day Til Cancelled
    ]

    user = models.ForeignKey(CustomUser, on_delete= models.CASCADE)
    accountId = models.CharField(max_length=100)
    conid = models.IntegerField()
    orderType = models.CharField(max_length=4, choices=ORDER_TYPE_CHOICES)
    price = models.IntegerField(blank=True, null=True)
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    tif = models.CharField(max_length=4, choices=TIF_CHOICES)
    quantity = models.IntegerField()
    exp_date = models.CharField(max_length=8, blank=True, null=True)  # Format: YYYYMMDD
    exp_time = models.CharField(max_length=8, blank=True, null=True)  # Format: HH:MM(:SS)

    def __str__(self):
        return f"{self.user.username} - {self.conid} - {self.quantity}"

#DUA785929