import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ForeignKey
from django.utils.timezone import now
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
        ('30-mins', '30min'),
        ('15-mins', '15min'),
        ('5-mins', '5min'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, blank=True, null=True)
    ticker_data = models.JSONField(blank=True, null=True)
    analysis_time = models.IntegerField(blank=True, null=True)
    time_frame = models.CharField(max_length=100, choices=TIME_FRAME_CHOICES, blank=True, null=True)
    time_steps = models.IntegerField(blank=True, null=True)
    confidence_level = models.IntegerField(blank=True, null=True)
    contract_expiry = models.IntegerField(blank=True, null=True)
    contract_id = models.CharField(max_length=100, blank=True, null=True)
    contract_month = models.CharField(max_length=50, blank=True, null=True)
    contract_trading_months = models.TextField(blank=True, null=True)
    no_of_contracts = models.IntegerField(blank=True, null=True)
    contract_type = models.CharField(max_length=4, choices=CONTRACT_TYPE_CHOICES, blank=True, null=True)
    upper_bound = models.FloatField(blank=True, null=True)
    lower_bound = models.FloatField(blank=True, null=True)
    form_step = models.PositiveIntegerField(default=0)
    validate_strikes_task = models.ForeignKey(PeriodicTask, on_delete=models.CASCADE, blank=True, null=True)

    def __str__(self):
        return f"{self.user.email} - {self.instrument} - {self.created_at}"

    @property
    def contract_leg_type(self):
        if self.contract_type == 'both':
            return 'DOUBLE LEG'
        elif not self.contract_type:
            return None
        return 'SINGLE LEG'


class TradingStatus(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    status = models.CharField(max_length=1, blank=True, null=True)
    wait_time = models.IntegerField()

    def __str__(self):
        return f"{self.user.email} - {self.status} - {self.wait_time} minutes"


class TimerData(BaseModel):
    user= models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    timer_value = models.IntegerField()
    original_timer_value = models.IntegerField()
    original_time_start = models.TimeField(blank=True, null=True)
    start_time = models.TimeField()
    place_order = models.CharField(max_length=5, blank=True, null=True)
    system_data = models.ForeignKey(SystemData, on_delete=models.CASCADE, blank=True, null=True)


    def __str__(self):
        return f"{self.timer_value}-{self.user.email}-{self.created_at}"


class PlaceOrder(BaseModel):
    ORDER_TYPE_CHOICES =[
        ('LMT', 'LMT'),
        ('MKT', 'MKT'),
        ('STP', 'STP')
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
    system_data = models.ForeignKey(SystemData, on_delete=models.SET_NULL, blank=True, null=True)
    user = models.ForeignKey(CustomUser, on_delete= models.CASCADE)
    accountId = models.CharField(max_length=100)
    conid = models.IntegerField()
    con_desc2 = models.CharField(max_length=500, blank=True, null=True)
    optionType = models.CharField(max_length=10)
    orderType = models.CharField(max_length=4, choices=ORDER_TYPE_CHOICES)
    customer_order_id = models.CharField(max_length=100)
    price = models.FloatField(blank=True, null=True)
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    tif = models.CharField(max_length=4, choices=TIF_CHOICES)
    quantity = models.IntegerField()
    limit_sell = models.FloatField(blank=True, null=True)
    stop_loss = models.FloatField(blank=True, null=True)
    take_profit = models.FloatField(blank=True, null=True)
    average_price = models.FloatField(blank=True, null=True)
    order_api_response = models.JSONField(blank=True, null=True)
    order_status = models.CharField(max_length=100, blank=True, null=True)
    is_cancelled = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.conid} - {self.quantity} - {self.created_at}"


class Strikes(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, blank=True, null=True)
    contract_id = models.CharField(max_length=255)
    strike_info = models.JSONField(blank=True, null=True)
    strike_price = models.FloatField()
    last_price = models.FloatField()
    is_valid = models.BooleanField(blank=True, null=True)
    month = models.CharField(max_length=15, blank=True, null=True)
    right = models.CharField(max_length=10) # tells if the strike is for Put or Call
