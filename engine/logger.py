import logging
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener, SMTPHandler
from pathlib import Path
import sys
import datetime
import json
import re
from queue import Queue

try:
    import colorlog
    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "vivian.log"
ERROR_LOG_FILE = LOG_DIR / "error.log"
AUDIT_LOG_FILE = LOG_DIR / "audit.log"

# Patterns to redact sensitive data (add more as needed)
REDACT_PATTERNS = [
    re.compile(r"(api[_-]?key\s*=\s*)\w+", re.I),
    re.compile(r"(token\s*=\s*)\w+", re.I),
    re.compile(r"(password\s*=\s*)\w+", re.I),
    re.compile(r"(Authorization:\s*)\S+", re.I),
]

def redact_message(msg):
    for pat in REDACT_PATTERNS:
        msg = pat.sub(r"\1[REDACTED]", msg)
    return msg

class RedactingFormatter(logging.Formatter):
    def format(self, record):
        original_msg = super().format(record)
        return redact_message(original_msg)

class JsonFormatter(logging.Formatter):
    def format(self, record):
        logrecord = {
            "timestamp": self.formatTime(record, self.datefmt or "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_message(record.getMessage()),
            "module": record.module,
            "funcName": record.funcName,
        }
        if record.exc_info:
            logrecord["exc_info"] = self.formatException(record.exc_info)
        # Add extra fields if present
        if hasattr(record, 'user'):
            logrecord['user'] = record.user
        if hasattr(record, 'session'):
            logrecord['session'] = record.session
        return json.dumps(logrecord)

def setup_logging(
    debug: bool = False,
    json_logs: bool = False,
    retention_days: int = 14,
    email_alerts: bool = False,
    alert_emails: list = None,
    smtp_config: dict = None,
    log_sampling_rate: int = 1
):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_level = logging.DEBUG if debug else logging.INFO

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # File handlers with timed rotation
    file_handler = TimedRotatingFileHandler(LOG_FILE, when='midnight', backupCount=retention_days, encoding="utf-8")
    error_handler = TimedRotatingFileHandler(ERROR_LOG_FILE, when='midnight', backupCount=retention_days, encoding="utf-8")
    audit_handler = TimedRotatingFileHandler(AUDIT_LOG_FILE, when='midnight', backupCount=retention_days, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    audit_handler.setLevel(logging.INFO)

    if json_logs:
        formatter = JsonFormatter()
    else:
        formatter = RedactingFormatter(log_format, datefmt=datefmt)

    file_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    audit_handler.setFormatter(formatter)

    # Console handler (with color if available)
    if COLORLOG_AVAILABLE and not json_logs:
        console_handler = colorlog.StreamHandler(sys.stdout)
        color_fmt = "%(log_color)s" + log_format
        console_handler.setFormatter(colorlog.ColoredFormatter(color_fmt, datefmt=datefmt))
    else:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

    handlers = [file_handler, error_handler, audit_handler, console_handler]

    # Optional: Email alerts for CRITICAL errors
    if email_alerts and alert_emails and smtp_config:
        email_handler = SMTPHandler(
            mailhost=(smtp_config.get("host"), smtp_config.get("port", 587)),
            fromaddr=smtp_config.get("from"),
            toaddrs=alert_emails,
            subject="Vivian CRITICAL ERROR",
            credentials=(smtp_config.get("user"), smtp_config.get("password")),
            secure=() if smtp_config.get("tls", True) else None
        )
        email_handler.setLevel(logging.CRITICAL)
        email_handler.setFormatter(formatter)
        handlers.append(email_handler)

    # Async logging setup
    log_queue = Queue(-1)
    queue_handler = QueueHandler(log_queue)
    listener = QueueListener(log_queue, *handlers)
    listener.start()

    # Log sampling filter
    class SamplingFilter(logging.Filter):
        def __init__(self, rate):
            super().__init__()
            self.rate = max(1, rate)
            self.counter = 0

        def filter(self, record):
            self.counter += 1
            return (self.counter % self.rate) == 0

    if log_sampling_rate > 1:
        queue_handler.addFilter(SamplingFilter(log_sampling_rate))

    logging.basicConfig(
        level=log_level,
        handlers=[queue_handler],
        force=True  # Python 3.8+: overrides previous handlers
    )

    logging.info("[Logger] Logging initialized (debug=%s, json=%s, async=%s, sampling_rate=%d)",
                 debug, json_logs, True, log_sampling_rate)

def log_exception(e: Exception, context: str = "General", extra: dict = None, audit: bool = False):
    logger = logging.getLogger("Vivian.Audit" if audit else context)
    logger.error(f"{type(e).__name__}: {e}", exc_info=True, extra=extra or {})

def log_event(message: str, level: str = "info", extra: dict = None, audit: bool = False):
    logger = logging.getLogger("Vivian.Audit" if audit else "Vivian")
    if level == "debug":
        logger.debug(message, extra=extra or {})
    elif level == "warning":
        logger.warning(message, extra=extra or {})
    elif level == "error":
        logger.error(message, extra=extra or {})
    elif level == "critical":
        logger.critical(message, extra=extra or {})
    else:
        logger.info(message, extra=extra or {})

def set_log_level(level):
    """Dynamically set global log level."""
    logging.getLogger().setLevel(level)

def tail_log(logfile=LOG_FILE, lines=20):
    """Simple CLI utility to tail logs."""
    try:
        with open(logfile, "r", encoding="utf-8") as f:
            print("".join(f.readlines()[-lines:]))
    except Exception as e:
        print(f"[Logger] Could not tail log file: {e}")

def search_logs(keyword, logfile=LOG_FILE, lines=100):
    """Simple CLI utility to search logs."""
    try:
        with open(logfile, "r", encoding="utf-8") as f:
            matched = [line for line in f if keyword in line]
        print("".join(matched[-lines:]))
    except Exception as e:
        print(f"[Logger] Could not search log file: {e}")

# Example: user/session context with LoggerAdapter
class VivianLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[user={self.extra.get('user', '?')}] {msg}", kwargs

# For direct CLI/testing
if __name__ == "__main__":
    setup_logging(
        debug=True,
        json_logs=False,
        retention_days=7,
        email_alerts=False,
        log_sampling_rate=1
    )
    log_event("Vivian logger test message.")
    log_event("Vivian audit event", audit=True, extra={"user": "admin"})
    try:
        raise ValueError("Test error for Vivian logger")
    except Exception as e:
        log_exception(e, "LoggerTest", extra={"user": "testuser"})
    print("\n--- Last 10 log lines ---")
    tail_log(lines=10)