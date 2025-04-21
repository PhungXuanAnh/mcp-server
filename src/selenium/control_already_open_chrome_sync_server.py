# Standard library imports
import logging
import time
import socket
import subprocess
from datetime import datetime
from enum import Enum
from logging.config import dictConfig
from pathlib import Path
from typing import Optional, Tuple

# Third-party imports
import click
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions

# Configure logging
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
            "maxBytes": 100000 * 1024,  # 100MB
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

# Initialize logging
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# Global variable to store WebDriver instance
driver = None

# Initialize FastMCP
mcp = FastMCP(
    name="mcp-selenium-sync",
)

# Define the data models for our tools
class Navigate(BaseModel):
    url: str
    timeout: int = Field(default=60, description="Timeout in seconds for page load")

class TakeScreenshot(BaseModel):
    pass

class CheckPageReady(BaseModel):
    wait_seconds: int = Field(default=0, description="Optional seconds to wait before checking")

def check_chrome_debugger_port(port: int = 9222) -> bool:
    """Check if Chrome is running with remote debugging port open"""
    try:
        # Try to connect to the port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0
    except Exception as e:
        logger.error(f"Error checking Chrome debugger port: {str(e)}")
        return False

def start_chrome(port: int = 9222) -> bool:
    """Start Chrome with remote debugging enabled on specified port"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_data_dir = f"/tmp/chrome-debug-{timestamp}"
        
        logger.info(f"Starting Chrome with debugging port {port} and user data dir {user_data_dir}")
        
        # Start Chrome as a subprocess
        cmd = [
            "google-chrome-stable",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            start_new_session=True  # Detach from the parent process
        )
        
        # Wait a moment for Chrome to start
        time.sleep(3)
        
        # Check if Chrome started correctly
        if check_chrome_debugger_port(port):
            logger.info(f"Chrome started successfully on port {port}")
            return True
        else:
            logger.error("Failed to start Chrome or confirm debugging port is open")
            return False
    except Exception as e:
        logger.error(f"Error starting Chrome: {str(e)}")
        return False

def initialize_driver(browser: str = "chrome", headless: bool = False) -> webdriver.Remote:
    """Initialize and return a WebDriver instance based on browser choice"""
    global driver
    
    if browser.lower() != "chrome":
        raise ValueError(f"Unsupported browser: {browser}. Only Chrome is supported.")
    
    # Check if Chrome is already running with remote debugging
    if not check_chrome_debugger_port():
        logger.info("Chrome not detected on port 9222, attempting to start a new instance")
        if not start_chrome():
            raise RuntimeError("Failed to start Chrome browser")
    else:
        logger.info("Chrome already running with remote debugging port 9222")
        
    options = ChromeOptions()
    
    # Connect to Chrome instance with remote debugging port
    options.debugger_address = "127.0.0.1:9222"
    
    # Create the driver without specifying service or additional options
    driver = webdriver.Chrome(options=options)
    
    # Set longer page load timeout
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    
    return driver

@mcp.tool()
def selenium_navigate(url: str, timeout: int = 60) -> str:
    """Navigate to a specified URL with configurable timeout"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    logger.info(f"Starting navigation to {url} with timeout {timeout} seconds")
    
    # Ensure URL has a proper protocol (http:// or https://)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        logger.info(f"Added https:// protocol, URL is now {url}")
    
    # Use a shorter timeout for navigation to avoid MCP timeout
    navigation_timeout = min(timeout, 5)  # Limit to 5 seconds for initial navigation
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

@mcp.tool()
def selenium_take_screenshot() -> str:
    """Take a screenshot of the current page"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    # Create the screenshot directory if it doesn't exist
    screenshot_dir = Path.home() / "selenium-mcp" / "screenshot"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate a filename automatically
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    
    screenshot_path = screenshot_dir / filename
    driver.save_screenshot(str(screenshot_path))
    
    return f"Screenshot saved to {screenshot_path}"

@mcp.tool()
def selenium_check_page_ready(wait_seconds: int = 0) -> str:
    """Check the document.readyState of the current page"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
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

# Main entry point
if __name__ == "__main__":
    @click.command()
    @click.option("--browser", "-b", default="chrome", help="Browser to use (chrome)")
    @click.option("--headless", is_flag=True, help="Run browser in headless mode")
    @click.option("-v", "--verbose", count=True)
    def main(browser: str, headless: bool, verbose: int) -> None:
        """Selenium MCP Server - Synchronous version"""
        # Setup logging based on verbosity
        if verbose == 1:
            logging.getLogger().setLevel(logging.INFO)
        elif verbose >= 2:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Initialize the WebDriver
        logger.info(f"Checking for Chrome instance at 127.0.0.1:9222")
        try:
            initialize_driver(browser, headless)
            logger.info("WebDriver initialized successfully")
            
            # Run the MCP server
            logger.info("Starting MCP Selenium server")
            mcp.run(transport='stdio')
            
        except Exception as e:
            logger.error(f"Error starting server: {str(e)}")
        
        finally:
            # Clean up the WebDriver when done, but don't close the browser
            # since we're connecting to an existing instance
            if driver is not None:
                logger.info("Disconnecting from Chrome instance (but leaving browser open)")
                driver.quit()
    
    main() 