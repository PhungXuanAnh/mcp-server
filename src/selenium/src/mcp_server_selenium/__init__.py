import click
from pathlib import Path
import logging
from logging.config import dictConfig
import sys
from .server import serve


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[%(asctime)s] [%(pathname)s:%(lineno)d] [%(funcName)s] %(levelname)s: %(message)s"
        },
    },
    "handlers": {
        "app.DEBUG": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": "/tmp/app.log",
            "maxBytes": 100000 * 1024,  # 1Kb       #100 * 1024 * 1024,  # 100Mb
            "backupCount": 3,
        },
    },
    "loggers": {
        "root": {
            "handlers": ["app.DEBUG"],
            "propagate": False,
            "level": "DEBUG",
        },
    },
}


@click.command()
@click.option("--browser", "-b", default="chrome", help="Browser to use (chrome, firefox)")
@click.option("--headless", is_flag=True, help="Run browser in headless mode")
@click.option("-v", "--verbose", count=True)
def main(browser: str, headless: bool, verbose: bool) -> None:
    """MCP Selenium Server - Selenium WebDriver functionality for MCP"""
    import asyncio

    logging_level = logging.WARN
    if verbose == 1:
        logging_level = logging.INFO
    elif verbose >= 2:
        logging_level = logging.DEBUG

    # logging.basicConfig(level=logging_level, stream=sys.stderr)
    dictConfig(LOGGING_CONFIG)
    asyncio.run(serve(browser, headless))

if __name__ == "__main__":
    main() 