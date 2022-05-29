import logging
import os
from datetime import datetime

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

# Initialize logger
root_logger = logging.getLogger("k8s-sidecar")
log_handler = logging.StreamHandler()
log_level = level.upper() if isinstance(level, str) else level
log_tz = LogTimezones[tz.upper()] if LogTimezones.get(tz.upper()) else LogTimezones['LOCAL']


# Base Formatter to enforce time format in ISO8601 with LOCAL or UTC Timezone
class BaseFormatter(logging.Formatter):
    def formatTime(self, record, timeFormat=None):
        if timeFormat is not None:
            return super(BaseFormatter, self).formatTime(record, timeFormat)
        return datetime.fromtimestamp(record.created, log_tz).isoformat()


# Define formatter using LogFmt format (time in ISO8601)
class LogfmtFormatter(Logfmter, BaseFormatter):
    def __init__(self, keys, mapping):
        super(LogfmtFormatter, self).__init__(keys, mapping)


# Define formatter using Json format (time in ISO8601)
class JsonFormatter(BaseFormatter, jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(JsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('msg'):
            log_record['msg'] = log_record['message']
        if not log_record.get('time'):
            log_record['time'] = self.formatTime(record)
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname


# Supported Log Formatters
LogFormatters = {
    'JSON': (JsonFormatter('%(time)s %(level)s %(msg)s')),
    'LOGFMT': (LogfmtFormatter(keys=["time", "level", "msg"],
                               mapping={"time": "asctime", "level": "levelname", "msg": "message"}))
}

log_fmt = LogFormatters[fmt.upper()] if LogFormatters.get(fmt.upper()) else LogFormatters['DEFAULT']

try:
    log_handler.setFormatter(log_fmt)
    root_logger.addHandler(log_handler)
    root_logger.setLevel(log_level)
except (ValueError, TypeError) as e:
    root_logger.warning(f"Initializing default logger", exc_info=True)
    root_logger.setLevel(logging.INFO)
    log_handler.setFormatter(log_fmt)

root_logger.addHandler(log_handler)


def get_logger():
    return root_logger
