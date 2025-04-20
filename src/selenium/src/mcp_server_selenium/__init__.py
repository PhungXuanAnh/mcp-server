import click
from pathlib import Path
import logging
import sys
from .server import serve

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

    logging.basicConfig(level=logging_level, stream=sys.stderr)
    asyncio.run(serve(browser, headless))

if __name__ == "__main__":
    main() 