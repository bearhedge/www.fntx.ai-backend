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