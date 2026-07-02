import logging
import logging.handlers
import sys
import os
from datetime import datetime

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)


def configure_logging(log_level: str = "INFO") -> None:
    log_level_value = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level_value)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    error_file_path = os.path.join(LOGS_DIR, f"error_{datetime.now().strftime('%Y%m%d')}.log")
    error_handler = logging.handlers.RotatingFileHandler(
        error_file_path, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    info_file_path = os.path.join(LOGS_DIR, f"app_{datetime.now().strftime('%Y%m%d')}.log")
    info_handler = logging.handlers.RotatingFileHandler(
        info_file_path, maxBytes=10 * 1024 * 1024, backupCount=10
    )
    info_handler.setLevel(log_level_value)
    info_handler.setFormatter(formatter)
    root_logger.addHandler(info_handler)

    root_logger.info(f"Logging configured with level: {log_level}")
    root_logger.info(f"Log files location: {LOGS_DIR}")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def configure_uvicorn_logging() -> None:
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.setLevel(logging.INFO)
    
    if not uvicorn_logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        
        app_log_file = os.path.join(LOGS_DIR, f"app_{datetime.now().strftime('%Y%m%d')}.log")
        handler = logging.handlers.RotatingFileHandler(
            app_log_file, maxBytes=10 * 1024 * 1024, backupCount=10
        )
        handler.setFormatter(formatter)
        uvicorn_logger.addHandler(handler)
