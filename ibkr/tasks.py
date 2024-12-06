from celery import shared_task
import requests
from django.conf import settings
from django_celery_beat.models import PeriodicTask

from core.views import IBKRBase
from ibkr.models import OnBoardingProcess


@shared_task
def tickle_ibkr_session(data):
    """
    Task to hit the IBKR tickle API every 2 minutes to maintain the session.
    """
    try:
        onboarding_id = data.get('onboarding_id')
        user_id = data.get('user_id')
        task_id = data.get('task_id')
        onboarding_obj = OnBoardingProcess.objects.filter(id=onboarding_id, user_id=user_id).first()
        auth_fail = False
        ibkr = IBKRBase()
        response = ibkr.auth_status()
        if response.get('success'):
            tickle_url = f"{settings.IBKR_BASE_URL}/tickle"
            response = requests.post(tickle_url, verify=False)

            if not response.status_code == 200:
                auth_fail = True
                return {
                    "message": "Failed to tickle IBKR session",
                    "status_code": response.status_code,
                }
        else:
            auth_fail = True

        if auth_fail:
            onboarding_obj.authenticated = False
            onboarding_obj.save()

            # disable the task
            task = PeriodicTask.objects.get(id=task_id)
            task.enabled = False
            task.save()
    except requests.exceptions.RequestException as e:
        return {"error": "Error hitting IBKR tickle endpoint", "details": str(e)}
