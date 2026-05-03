import sys
import os
from loguru import logger

from config import config

os.makedirs(config.LOG_DIR, exist_ok=True)


class MyLogger:
    def __init__(self):
        self.logger = logger
        self.logger.remove()
        self.logger.add(
            sys.stdout,
            level=config.LOG_LEVEL,
            format=(
                "<green>{time:YYYYMMDD HH:mm:ss}</green> | "
                "{process.name} | "
                "{thread.name} | "
                "<cyan>{module}</cyan>.<cyan>{function}</cyan>"
                ":<cyan>{line}</cyan> | "
                "<level>{level}</level>: "
                "<level>{message}</level>"
            ),
        )

    def get_logger(self):
        return self.logger


log = MyLogger().get_logger()
