import json
import re
from django.contrib.auth.hashers import make_password
from django_celery_beat.models import PeriodicTask, IntervalSchedule
from django.utils.translation import gettext_lazy as _lazy


from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


from accounts.models import CustomUser
from ibkr.models import OnBoardingProcess


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CustomUser
        exclude = ["last_login", "is_staff", "is_active", "is_superuser", "otp"]

        extra_kwargs = {
            "username": {"required": True},
            "email": {"required": True},
        }

    def validate_email(self, value):
        """
        Custom validation for the email field.
        """
        if CustomUser.objects.filter(email__icontains=value).exists():
            raise serializers.ValidationError("User with this email has already been registered.")
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        if not len(password) >= 8:
            raise serializers.ValidationError(
                "Password length should be more than 8"
            )
        elif not re.findall("[A-Z]", password):
            raise serializers.ValidationError(
                "The password must contain at least 1 uppercase letter, A-Z."
            )
        elif not re.findall("[a-z]", password):
            raise serializers.ValidationError(
                "The password must contain at least 1 lowercase letter, a-z."
            )

        return attrs


    def create(self, validated_data):
        password = validated_data.pop('password', None)
        instance = CustomUser.objects.create(**validated_data)
        instance.password = make_password(password)
        instance.save()

        return instance

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.password = make_password(password)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        exclude = ["password", "last_login", "is_active"]



class UserTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = "email"
    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        # Ensure email and password are provided
        if not email or not password:
            raise serializers.ValidationError(
                {"error": _lazy('Must include "email" and "password".')}
            )

        try:
            user = CustomUser.objects.get(email__icontains=email, is_active=True, is_superuser=False)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError(
                {"error": _lazy("Account with this email does not exist.")}
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {"error": _lazy("This account is inactive.")}
            )

        if not user.check_password(password):
            raise serializers.ValidationError(
                {"error": _lazy("Incorrect password. Please try again.")}
            )

        refresh = self.get_token(user)

        # Check or create onboarding process entry
        onboarding_process, created = OnBoardingProcess.objects.get_or_create(user=user)

        # Create periodic task
        task_name = f"tickle_ibkr_session_user_{user.id}"
        if not PeriodicTask.objects.filter(name=task_name).exists():
            interval_schedule, _ = IntervalSchedule.objects.get_or_create(
                every=3, period=IntervalSchedule.SECONDS
            )

            periodic_task = PeriodicTask.objects.create(
                interval=interval_schedule,
                name=task_name,
                task="ibkr.tasks.tickle_ibkr_session",
                enabled=True
            )

            # save the args of the task
            args = [{"user_id": str(user.id), "task_id": periodic_task.id, "onboarding_id": str(onboarding_process.id)}]
            periodic_task.args = json.dumps(args)
            periodic_task.save()

            # Link periodic task to the onboarding process
            onboarding_process.periodic_task = periodic_task
            onboarding_process.save()
        else:
            task = onboarding_process.periodic_task
            task.enabled = True
            task.save()

        data = {"refresh": str(refresh), "access": str(refresh.access_token), "user": {
            "username": user.username,
            "email": user.email,
            "ibkr_authentication": onboarding_process.authenticated if onboarding_process else None,
            "level_4_permission": onboarding_process.level_4_permission if onboarding_process else None,
            "active_subscription": onboarding_process.active_subscription if onboarding_process else None,
            "metamask_address": onboarding_process.metamask_address if onboarding_process else None
        }}

        return data


    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Adding custom claims here
        token["email"] = user.email
        return token

    def user_can_authenticate(self, user):
        return getattr(user, "is_active", None)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    confirm_new_password = serializers.CharField(required=True)

    class Meta:
        fields = ["old_password", "new_password", "confirm_new_password"]

    def validate(self, attrs):
        old_password = attrs.get("old_password")
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_new_password")
        username = self.context["request"].user
        user = CustomUser.objects.get(username=username)
        if user:
            if user.check_password(old_password):
                if old_password == new_password:
                    raise serializers.ValidationError(
                        "Password already has been used by you previous time please enter new "
                        "password."
                    )
            else:
                raise serializers.ValidationError(
                    "old password you entered is incorrect."
                )
        else:
            raise serializers.ValidationError("invalid credentials.")
        if new_password != confirm_password:
            raise serializers.ValidationError(
                "New password do not match with confirm password."
            )
        elif not len(new_password) >= 8:
            raise serializers.ValidationError("Password length should be more than 8")
        elif not re.findall("[A-Z]", new_password):
            raise serializers.ValidationError(
                "The password must contain at least 1 uppercase letter, A-Z."
            )
        elif not re.findall("[a-z]", new_password):
            raise serializers.ValidationError(
                "The password must contain at least 1 lowercase letter, a-z."
            )
        return attrs

    def create(self, data):
        new_password = data.get("new_password")
        username = self.context["request"].user
        user = CustomUser.objects.get(username=username)

        if user:
            user.set_password(new_password)
            user.save()
        return data


class OTPEmailVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not CustomUser.objects.filter(email__icontains=value).exists():
            raise serializers.ValidationError("No user exists with the provided email.")
        else:
            return value

    class Meta:
        fields = "__all__"
        abstract = True


class SendOTPSerializer(OTPEmailVerifySerializer):
    pass


class ForgotPasswordSerializer(OTPEmailVerifySerializer):
    otp = serializers.CharField()
    password = serializers.CharField()