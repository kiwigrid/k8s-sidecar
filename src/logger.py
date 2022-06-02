import logging
import os
from datetime import datetime
from typing import Optional

from dateutil.tz import tzlocal, tzutc
from logfmter import Logfmter
from pythonjsonlogger import jsonlogger

# Supported Timezones for time format (in ISO 8601)
LogTimezones = {
    'LOCAL': tzlocal(),
    'UTC': tzutc()
}

# Get configuration
level = os.getenv("LOG_LEVEL", logging.INFO)
fmt = os.getenv("LOG_FORMAT", 'JSON')
tz = os.getenv("LOG_TZ", 'LOCAL')

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
root_logger = logging.getLogger()
log_handler = logging.StreamHandler()
log_handler.setFormatter(log_fmt)
root_logger.addHandler(log_handler)
root_logger.setLevel(level.upper() if isinstance(level, str) else level)
root_logger.addHandler(log_handler)


def get_logger():
    return logging.getLogger('k8s-sidecar')