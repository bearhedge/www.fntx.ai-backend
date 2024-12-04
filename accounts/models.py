# accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, UserManager
from django.db import models

from core.models import BaseModel


class CustomUser(AbstractBaseUser, BaseModel):
    username = models.CharField(max_length=50, unique=True, error_messages={'unique':"User with this username has already been registered."})
    email = models.EmailField(unique=True, error_messages={'unique':"User with this email has already been registered."})
    otp = models.CharField(max_length=10, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)


    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']
    objects = UserManager()


    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.username

    def has_perm(self, perm, obj=None):
        """
        Does the user have a specific permission?
        """
        return True

    def has_module_perms(self, app_label):
        return True
