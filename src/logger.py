import logging
import os
from datetime import datetime
from typing import Optional

from dateutil.tz import tzlocal, tzutc
from logfmter import Logfmter
from pythonjsonlogger import jsonlogger
from logging.handlers import RotatingFileHandler

# Supported Timezones for time format (in ISO 8601)
LogTimezones = {
    'LOCAL': tzlocal(),
    'UTC': tzutc()
}

# Get configuration
level = os.getenv("LOG_LEVEL", logging.INFO)
fmt = os.getenv("LOG_FORMAT", 'JSON')
tz = os.getenv("LOG_TZ", 'LOCAL')
#Possible values are CONSOLE, FILE, BOTH
log_mode = os.getenv("LOG_MODE","CONSOLE")
# If not specified default size of 2MB is set. 
log_file_maxsize = 2097152 if os.getenv("LOG_FILE_SIZE") is None else int(os.getenv("LOG_FILE_SIZE"))
log_num_files = 5 if os.getenv("LOG_MAX_FILES") is None else int(os.getenv("LOG_MAX_FILES"))
log_file_name = os.getenv("LOG_FILE_NAME","/tmp/kiwi-grid.log")
log_tz = LogTimezones[tz.upper()] if LogTimezones.get(tz.upper()) else LogTimezones['LOCAL']


class Iso8601Formatter:
    """
    A formatter mixin which always forces dates to be rendered in iso format.
    Using `datefmt` parameter of logging.Formatter is insufficient because of missing fractional seconds.
    """

    def formatTime(self, record, datefmt: Optional[str] = ...):
        """
        Meant to override logging.Formatter.formatTime
        """
        return datetime.fromtimestamp(record.created, log_tz).isoformat()


class LogfmtFormatter(Iso8601Formatter, Logfmter):
    """
    A formatter combining logfmt style with iso dates
    """
    pass


class JsonFormatter(Iso8601Formatter, jsonlogger.JsonFormatter):
    """
    A formatter combining json logs with iso dates
    """

    def add_fields(self, log_record, record, message_dict):
        log_record['time'] = self.formatTime(record)
        super(JsonFormatter, self).add_fields(log_record, record, message_dict)


# Supported Log Formatters
LogFormatters = {
    'JSON': (JsonFormatter('%(levelname)s %(message)s',
                           rename_fields={"message": "msg", "levelname": "level"})),
    'LOGFMT': (LogfmtFormatter(keys=["time", "level", "msg"],
                               mapping={"time": "asctime", "level": "levelname", "msg": "message"}))
}

log_fmt = LogFormatters[fmt.upper()] if LogFormatters.get(fmt.upper()) else LogFormatters['JSON']

# Initialize/configure root logger
def init_logger():
    root_logger = logging.getLogger()
    logLevel = level.upper() if isinstance(level, str) else level
    if log_mode == "CONSOLE" or log_mode == "BOTH":
        log_handler = logging.StreamHandler()
        log_handler.setFormatter(log_fmt)
        log_handler.setLevel(logLevel)
        root_logger.addHandler(log_handler)

    if log_mode == "FILE" or log_mode == "BOTH":
        stream_handler = RotatingFileHandler(log_file_name,'a',maxBytes=int(log_file_maxsize),backupCount=int(log_num_files))
        stream_handler.setFormatter(log_fmt)
        stream_handler.setLevel(logLevel)
        root_logger.addHandler(stream_handler)

    root_logger.setLevel(logLevel)


def get_logger():
    return logging.getLogger('k8s-sidecar')