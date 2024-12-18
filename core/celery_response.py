import sys
import os
import logging
import traceback
import json

logger = logging.getLogger(__name__)


def log_task_status(task_name, message=None, exception=None, additional_data=None):
    """
    Logs the success or failure status of a task with detailed error information if it fails.

    Args:
        task_name (str): Name of the task or endpoint.
        message (str): Message to log in case of success.
        exception (Exception): Exception object if an error occurs.
        additional_data (dict): Additional data to include in logs or meta info.

    Returns:
        dict: A dictionary containing the log details.
    """
    if exception is None:
        log_data = {
            "Task Name": task_name,
            "Status": "SUCCESS",
            "Message": message,
            "Additional Data": additional_data or {}
        }
        logger.info(json.dumps(log_data, indent=4))
        return log_data
    else:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        filename = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log_data = {
            "Task Name": task_name,
            "Status": "FAILURE",
            "Exception Type": str(exc_type),
            "Filename": str(filename),
            "Line Number": exc_tb.tb_lineno,
            "Exception Description": str(exception),
            "Traceback": traceback.format_exc(),
            "Additional Data": additional_data or {}
        }
        logger.error(json.dumps(log_data, indent=4))
        return log_data
