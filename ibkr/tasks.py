from datetime import timedelta, datetime

import requests


from celery import shared_task
from django.conf import settings
from django_celery_beat.models import PeriodicTask

from core.celery_response import log_task_status
from core.views import IBKRBase
from ibkr.models import OnBoardingProcess, TimerData


@shared_task(bind=True)
def tickle_ibkr_session(self, data=None):
    """
    Task to hit the IBKR tickle API every 2 minutes to maintain the session.
    """
    task_name = "tickle_ibkr_session"
    onboarding_id = data.get('onboarding_id')
    user_id = data.get('user_id')
    task_id = data.get('task_id')

    onboarding_obj = OnBoardingProcess.objects.filter(id=onboarding_id, user_id=user_id).first()
    if not onboarding_obj:
        log_task_status(task_name, message="Onboarding instance not found.", additional_data={"onboarding_id": onboarding_id})


    ibkr = IBKRBase()
    response = ibkr.auth_status()

    if not response.get('success'):
        return _disable_task_and_update_status(onboarding_obj, task_id)

    tickle_url = f"{settings.IBKR_BASE_URL}/tickle"

    try:
        tickle_response = requests.post(tickle_url, verify=False)
        if tickle_response.status_code != 200:
            return _disable_task_and_update_status(onboarding_obj, task_id, task_name)
    except requests.exceptions.RequestException as e:
        error_details = log_task_status(task_name, exception=e, additional_data={"payload": data})
        self.update_state(state="FAILURE", meta=error_details)
        raise

@shared_task(bind=True)
def update_timer(self, timer_id):
    task_name = "update_timer"
    try:
        # Perform the task logic
        timer = TimerData.objects.get(id=timer_id)
        if timer.timer_value > 0:
            timer.timer_value -= 1

            # increase time by 1 minute
            timer_start_time = timer.start_time
            current_datetime = datetime.combine(datetime.today(), timer_start_time)
            updated_datetime = current_datetime + timedelta(minutes=1)
            timer.start_time = updated_datetime.time()
            timer.save()
            success_details = log_task_status(task_name, message="Timer updated successfully", additional_data={"timer_id": timer_id})
        else:
            timer.place_order = False
            timer.save()
            success_details = log_task_status(task_name, message="Timer completed", additional_data={"timer_id": timer_id})
        self.update_state(state="SUCCESS", meta=success_details)

    except Exception as e:
        error_details = log_task_status(task_name, exception=e, additional_data={"timer_id": timer_id})
        self.update_state(state="FAILURE", meta=error_details)
        raise

def _disable_task_and_update_status(onboarding_obj, task_id, task_name):
    """
    Helper function to disable a task and update onboarding status.
    """
    onboarding_obj.authenticated = False
    onboarding_obj.save()

    task = PeriodicTask.objects.filter(id=task_id).first()
    if task:
        task.enabled = False
        task.save()

    return log_task_status(task_name, message="Authentication failed. Task disabled.", additional_data={"timer_id": task_id})
