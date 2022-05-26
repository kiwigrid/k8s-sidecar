import json
import os
import time
import logging
import datetime
from enum import Enum
from abc import ABC


class BaseFormatter(ABC, logging.Formatter):

    def formatTime(self, record):
        """
        Return the creation time of the specified LogRecord as formatted text.
        This method should be called from format() by a formatter which
        wants to make use of a formatted time.
        It provides an ISO 8601 format with milliseconds.
        """
        ct = self.converter(record.created)
        ct_with_ms = time.mktime(ct) + (record.msecs / 1000)
        ct_full = datetime.datetime.fromtimestamp(ct_with_ms)
        return ct_full.isoformat()

    def get_fields(self, record):
        """
        Return a dict wth the following fields:
         - time: ISO 8601 format with milliseconds (from datetime.isoFormat)
         - level: Log level in uppercase letter
         - msg: the log message
        """
        fields = dict()
        fields['time'] = self.formatTime(record)
        fields['level'] = record.levelname
        fields['msg'] = record.getMessage()
        if record.exc_info:
            fields['exception'] = self.formatException(record.exc_info)
        if record.stack_info:
            fields['stack'] = self.formatStack(record.exc_info)
        return fields


class LogfmtFormatter(BaseFormatter):
    """
    Formatter in logfmt format.

    Example:
        time=2021-03-02T17:11:04.632448 level=INFO msg="Service is running!"
    """
    def format(self, record):
        fields = super().get_fields(record)
        log_format_msg = list(
            map(lambda key:
                '%s="%s"' % (key, fields.get(key).replace('"', '\\"').replace('\n', '\\n'))
                if key in ('msg', 'exception', 'stack')
                else '%s=%s' % (key, fields.get(key)), fields.keys())
        )
        return " ".join(log_format_msg)


class JsonFormatter(BaseFormatter):
    """
    Formatter in json format.

    Example:
        {"time": "2021-03-02T17:11:04.632448", "level":"INFO", "msg": "Service is running!"}
    """
    def format(self, record):
        fields = super().get_fields(record)
        return json.dumps(fields)


LogFormatters = {
    'JSON': JsonFormatter(),
    'LOGFMT': LogfmtFormatter(),
    'DEFAULT': LogfmtFormatter(),
}

default_level = os.getenv("LOG_LEVEL", logging.INFO)
default_fmt = os.getenv("LOG_FORMAT", 'DEFAULT')


def get_logger(name, level=default_level, fmt=default_fmt):
    """
    Instantiate a logger with the specified name, level and formatter.

    :param name: logger name
    :param level: logger level (default INFO)
    :param fmt: logger formatter (default LOGFMT)
    :return: a logger instance
    """
    log = logging.getLogger(name)
    ch = logging.StreamHandler()
    log_level = level.upper() if isinstance(level, str) else level
    log_format = LogFormatters[fmt.upper()] if LogFormatters.get(fmt.upper()) else LogFormatters['DEFAULT']

    try:
        ch.setFormatter(log_format)
        log.addHandler(ch)
        log.setLevel(log_level)
    except (ValueError, TypeError) as e:
        log.warning(f"Initializing default logger", exc_info=True)
        log.setLevel(logging.INFO)
        ch.setFormatter(log_format)

    log.addHandler(ch)
    return log
