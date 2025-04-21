# Standard library imports
import logging
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

# Third-party imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions


# Define the data models for our tools
class Navigate(BaseModel):
    url: str
    timeout: int = Field(default=60, description="Timeout in seconds for page load")

class TakeScreenshot(BaseModel):
    pass

class CheckPageReady(BaseModel):
    wait_seconds: int = Field(default=0, description="Optional seconds to wait before checking")

class SeleniumTools(str, Enum):
    NAVIGATE = "selenium_navigate"
    TAKE_SCREENSHOT = "selenium_take_screenshot"
    CHECK_PAGE_READY = "selenium_check_page_ready"

# Global variable to store WebDriver instance
driver = None

# Helper functions for Selenium operations
def initialize_driver(browser: str, headless: bool) -> webdriver.Remote:
    """Initialize and return a WebDriver instance based on browser choice"""
    global driver
    
    if browser.lower() != "chrome":
        raise ValueError(f"Unsupported browser: {browser}. Only Chrome is supported.")
        
    options = ChromeOptions()
    
    # Connect to an already running Chrome instance with remote debugging port
    options.debugger_address = "127.0.0.1:9222"
    
    # Note: When connecting to an existing browser, we don't need to set most
    # of the previous options as they're already set by the browser instance
    
    # Just create the driver without specifying service or additional options
    driver = webdriver.Chrome(options=options)
    
    # Set longer page load timeout
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    
    # No need to set window size as we're using an existing browser window
    
    return driver

def navigate_to_url(url: str, timeout: int = 60) -> str:
    """Navigate to the specified URL"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting navigation to {url} with timeout {timeout} seconds")
    
    # Ensure URL has a proper protocol (http:// or https://)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        logger.info(f"Added https:// protocol, URL is now {url}")
    
    # Use a shorter timeout for navigation to avoid MCP timeout
    navigation_timeout = min(timeout, 5)  # Limit to 15 seconds max for navigation
    driver.set_page_load_timeout(navigation_timeout)
    logger.info(f"Set page load timeout to {navigation_timeout} seconds")
    
    start_time = time.time()
    try:
        # Start navigation
        logger.info(f"Calling driver.get({url})")
        driver.get(url)
        elapsed = time.time() - start_time
        logger.info(f"driver.get() completed in {elapsed:.2f} seconds")
        
        # Return immediately after navigation starts
        return f"Navigation to {url} initiated"
        
    except TimeoutException:
        # This catches the initial navigation timeout
        elapsed = time.time() - start_time
        current_url = driver.current_url
        logger.info(f"Navigation timed out after {elapsed:.2f} seconds. Current URL: {current_url}")
        
        if current_url and current_url != "about:blank" and current_url != "data:,":
            return f"Navigation to {url} started but timed out after {navigation_timeout} seconds. You can use selenium_check_page_ready tool to check if the page is loaded. Current URL: {current_url}"
        else:
            return f"Navigation to {url} timed out after {navigation_timeout} seconds, but may continue loading. You can use selenium_check_page_ready tool to check if the page is loaded. Current URL: {current_url}"
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error after {elapsed:.2f} seconds while navigating to {url}: {str(e)}")
        raise Exception(f"Error navigating to {url}: {str(e)}")

def take_screenshot() -> str:
    """Take a screenshot of the current page"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    # Create the screenshot directory if it doesn't exist
    screenshot_dir = Path.home() / "selenium-mcp" / "screenshot"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    
    screenshot_path = screenshot_dir / filename
    driver.save_screenshot(str(screenshot_path))
    
    return f"Screenshot saved to {screenshot_path}"

def check_page_ready(wait_seconds: int = 0) -> str:
    """Check the document.readyState of the current page"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    logger = logging.getLogger(__name__)
    
    # Wait the specified number of seconds if requested
    if wait_seconds > 0:
        logger.info(f"Waiting {wait_seconds} seconds before checking page ready state")
        time.sleep(wait_seconds)
    
    try:
        # Get the current document.readyState
        ready_state = driver.execute_script('return document.readyState')
        current_url = driver.current_url
        
        logger.info(f"Current document.readyState: {ready_state}, URL: {current_url}")
        
        # Return a formatted response with details
        if ready_state == 'complete':
            return f"Page is fully loaded (readyState: {ready_state}) at URL: {current_url}"
        elif ready_state == 'interactive':
            return f"Page is partially loaded (readyState: {ready_state}) at URL: {current_url}"
        else:
            return f"Page is still loading (readyState: {ready_state}) at URL: {current_url}"
    
    except Exception as e:
        logger.error(f"Error checking page ready state: {str(e)}")
        raise Exception(f"Error checking page ready state: {str(e)}")

async def serve(browser: str, headless: bool) -> None:
    """Main server function"""
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize the WebDriver - only Chrome is supported
        if browser.lower() != "chrome":
            logger.warning(f"Browser {browser} is not supported, defaulting to Chrome")
            browser = "chrome"
            
        logger.info(f"Connecting to existing Chrome instance at 127.0.0.1:9222")
        # The headless parameter is ignored when connecting to existing instance
        initialize_driver("chrome", False)
        
        # Create the MCP server with increased timeout
        server: Server = Server("mcp-selenium")
        
        @server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name=SeleniumTools.NAVIGATE,
                    description="Navigate to a specified URL with configurable timeout",
                    inputSchema=Navigate.schema(),
                ),
                Tool(
                    name=SeleniumTools.TAKE_SCREENSHOT,
                    description="Take a screenshot of the current page",
                    inputSchema=TakeScreenshot.schema(),
                ),
                Tool(
                    name=SeleniumTools.CHECK_PAGE_READY,
                    description="Check the document.readyState of the current page",
                    inputSchema=CheckPageReady.schema(),
                ),
            ]
        
        @server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            logger.info(f"Calling tool: {name} with arguments: {arguments}")
            
            try:
                if name == SeleniumTools.NAVIGATE:
                    navigate_args = Navigate(**arguments)
                    # Ensure a reasonable timeout to avoid MCP timeout
                    if navigate_args.timeout > 20:
                        logger.info(f"Reducing timeout from {navigate_args.timeout} to 20 seconds to avoid MCP timeout")
                        navigate_args.timeout = 20
                    result = navigate_to_url(navigate_args.url, navigate_args.timeout)
                    return [TextContent(type="text", text=result)]
                
                elif name == SeleniumTools.TAKE_SCREENSHOT:
                    # No need to handle filename anymore since it's removed
                    result = take_screenshot()
                    return [TextContent(type="text", text=result)]
                
                elif name == SeleniumTools.CHECK_PAGE_READY:
                    check_ready_args = CheckPageReady(**arguments)
                    result = check_page_ready(check_ready_args.wait_seconds)
                    return [TextContent(type="text", text=result)]
                
                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
            
            except Exception as e:
                logger.error(f"Error calling tool {name}: {str(e)}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
        
        # Start the server with increased timeout
        logger.info("Starting MCP Selenium server")
        options = server.create_initialization_options()
        # The timeout option is not supported in this version of the MCP SDK
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)
        
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
    
    finally:
        # Clean up the WebDriver when done, but don't close the browser
        # since we're connecting to an existing instance
        if driver is not None:
            logger.info("Disconnecting from Chrome instance (but leaving browser open)")
            driver.quit() 
            
          

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

import logging
from logging.config import dictConfig
from pathlib import Path

import click

@click.command()
@click.option("--browser", "-b", default="chrome", help="Browser to use (chrome)")
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