from django.db import models

from accounts.models import CustomUser
from core.models import BaseModel


class OnBoardingProcess(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    authenticated = models.BooleanField(default=False)
    level_4_permission = models.BooleanField(default=False)
    active_subscription = models.BooleanField(default=False)
    metamask_address = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return self.user.email