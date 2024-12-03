from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def send_email(subject, body_text_content, recipient_list, html_content=None):
    email_message = EmailMultiAlternatives(
        subject=subject,
        body=body_text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )
    if html_content:
        email_message.attach_alternative(html_content, "text/html")
    email_message.send(fail_silently=True)
    return True