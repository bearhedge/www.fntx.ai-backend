from celery import shared_task
import requests
from django.conf import settings


@shared_task
def tickle_ibkr_session():
    """
    Task to hit the IBKR tickle API every 2 minutes to maintain the session.
    """
    try:
        tickle_url = f"{settings.IBKR_BASE_URL}/tickle"
        response = requests.post(tickle_url, verify=False)

        if response.status_code == 200:
            return {"message": "IBKR tickle successful", "status_code": 200}
        else:
            return {
                "message": "Failed to tickle IBKR session",
                "status_code": response.status_code,
            }
    except requests.exceptions.RequestException as e:
        return {"error": "Error hitting IBKR tickle endpoint", "details": str(e)}
