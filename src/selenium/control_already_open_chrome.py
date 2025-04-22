# Standard library imports
import logging
import time
import socket
import subprocess
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

# Third-party imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field

from selenium import webdriver
from selenium.common.exceptions import WebDriverException, TimeoutException, InvalidSessionIdException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Define the data models for our tools
class Navigate(BaseModel):
    url: str
    timeout: int = Field(default=60, description="Timeout in seconds for page load")

class TakeScreenshot(BaseModel):
    pass

class CheckPageReady(BaseModel):
    wait_seconds: int = Field(default=0, description="Optional seconds to wait before checking")

class GetConsoleLogs(BaseModel):
    pass

class GetConsoleErrors(BaseModel):
    pass

class GetNetworkLogs(BaseModel):
    pass

class GetNetworkErrors(BaseModel):
    pass

class SeleniumTools(str, Enum):
    NAVIGATE = "selenium_navigate"
    TAKE_SCREENSHOT = "selenium_take_screenshot"
    CHECK_PAGE_READY = "selenium_check_page_ready"
    GET_CONSOLE_LOGS = "selenium_get_console_logs"
    GET_CONSOLE_ERRORS = "selenium_get_console_errors"
    GET_NETWORK_LOGS = "selenium_get_network_logs"
    GET_NETWORK_ERRORS = "selenium_get_network_errors"

# Global variable to store WebDriver instance
driver: Optional[webdriver.Chrome] = None

# Helper functions for Selenium operations
def check_chrome_debugger_port(port: int = 9222) -> bool:
    """Check if Chrome is running with remote debugging port open"""
    try:
        # Try to connect to the port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error checking Chrome debugger port: {str(e)}")
        return False

def start_chrome(port: int = 9222) -> bool:
    """Start Chrome with remote debugging enabled on specified port"""
    logger = logging.getLogger(__name__)
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

def initialize_driver(browser: str, headless: bool) -> webdriver.Chrome:
    """Initialize and return a WebDriver instance based on browser choice"""
    global driver
    logger = logging.getLogger(__name__)
    
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
    
    # Note: When connecting to an existing browser, we don't need to set most
    # of the previous options as they're already set by the browser instance
    
    # Just create the driver without specifying service or additional options
    driver = webdriver.Chrome(options=options)
    
    # Set longer page load timeout
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    
    # No need to set window size as we're using an existing browser window
    
    return driver

def open_devtools_and_wait(panel: str) -> None:
    """Open Chrome DevTools and switch to specified panel"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    logger = logging.getLogger(__name__)
    logger.info(f"Opening DevTools with panel: {panel}")
    
    # Open DevTools
    driver.execute_script("window.open('chrome-devtools://devtools/bundled/devtools_app.html', 'devtools');")
    
    # Switch to DevTools tab
    original_window = driver.current_window_handle
    for window_handle in driver.window_handles:
        if window_handle != original_window:
            driver.switch_to.window(window_handle)
            break
    
    # Wait for DevTools to load
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".toolbar"))
        )
        
        # Switch to the specified panel
        if panel == "console":
            panel_script = """
            const panelButton = document.querySelector('.toolbar-button[aria-label="Console"]');
            if (panelButton) panelButton.click();
            """
        elif panel == "network":
            panel_script = """
            const panelButton = document.querySelector('.toolbar-button[aria-label="Network"]');
            if (panelButton) panelButton.click();
            """
        else:
            raise ValueError(f"Unsupported DevTools panel: {panel}")
        
        driver.execute_script(panel_script)
        time.sleep(1)  # Give the panel time to activate
        
    except Exception as e:
        logger.error(f"Error opening DevTools panel {panel}: {str(e)}")
        # Close DevTools tab and switch back to original
        driver.close()
        driver.switch_to.window(original_window)
        raise
    
    # Return to original window
    driver.switch_to.window(original_window)

def is_driver_session_valid() -> bool:
    """Check if the current WebDriver session is valid"""
    global driver
    logger = logging.getLogger(__name__)
    
    if driver is None:
        logger.info("WebDriver is not initialized")
        return False
    
    try:
        # Try a simple operation to check if the session is valid
        _ = driver.current_url
        return True
    except InvalidSessionIdException:
        logger.warning("Invalid session ID detected, WebDriver session is no longer valid")
        return False
    except WebDriverException as e:
        logger.warning(f"WebDriver exception when checking session: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking WebDriver session: {str(e)}")
        return False

def ensure_valid_driver() -> None:
    """Ensure we have a valid WebDriver instance, reinitialize if needed"""
    global driver
    logger = logging.getLogger(__name__)
    
    if not is_driver_session_valid():
        logger.info("WebDriver session is invalid, reinitializing...")
        # Close existing driver if it exists to clean up resources
        if driver is not None:
            try:
                driver.quit()
            except Exception as e:
                logger.warning(f"Error closing invalid driver: {str(e)}")
            finally:
                driver = None
        
        # Check if Chrome is still available with debugging port
        if check_chrome_debugger_port():
            try:
                initialize_driver("chrome", False)
                logger.info("Successfully reinitialized WebDriver")
            except Exception as e:
                logger.error(f"Failed to reinitialize WebDriver: {str(e)}")
                raise RuntimeError(f"Failed to reinitialize WebDriver: {str(e)}")
        else:
            logger.error("Chrome debugging port is no longer available")
            try:
                # Try starting Chrome again
                if start_chrome():
                    initialize_driver("chrome", False)
                    logger.info("Started Chrome and reinitialized WebDriver")
                else:
                    raise RuntimeError("Failed to start Chrome for WebDriver reinitialization")
            except Exception as e:
                logger.error(f"Failed to start Chrome and reinitialize WebDriver: {str(e)}")
                raise RuntimeError(f"Failed to start Chrome and reinitialize WebDriver: {str(e)}")

def get_devtools_logs(panel: str, log_type: str = "all") -> List[Dict[str, Any]]:
    """Get logs from DevTools panel"""
    global driver
    logger = logging.getLogger(__name__)
    
    # Ensure we have a valid driver
    ensure_valid_driver()
    
    # At this point, driver should definitely not be None
    if driver is None:
        # This shouldn't happen if ensure_valid_driver worked correctly, but just in case
        raise RuntimeError("WebDriver is not initialized after ensure_valid_driver")
    
    # Type annotation to help type checker
    from typing import cast
    driver_instance = cast(webdriver.Chrome, driver)
    
    # Store the current window handle before opening DevTools
    original_window = driver_instance.current_window_handle
    
    try:
        # Open DevTools with specified panel
        open_devtools_and_wait(panel)
        
        # Find DevTools window
        devtools_window = None
        for window_handle in driver_instance.window_handles:
            if window_handle != original_window:
                devtools_window = window_handle
                break
        
        if not devtools_window:
            raise RuntimeError("DevTools window not found")
        
        # Switch to DevTools window
        driver_instance.switch_to.window(devtools_window)
        
        # Execute appropriate script based on panel and log type
        if panel == "console":
            if log_type == "errors":
                script = """
                const logs = Array.from(document.querySelectorAll('.console-message-wrapper'))
                    .filter(el => el.classList.contains('console-error-level'))
                    .map(el => {
                        return {
                            type: 'error',
                            message: el.querySelector('.console-message-text').textContent,
                            timestamp: el.querySelector('.console-message-timestamp')?.textContent || ''
                        };
                    });
                return logs;
                """
            else:
                script = """
                const logs = Array.from(document.querySelectorAll('.console-message-wrapper'))
                    .map(el => {
                        let type = 'info';
                        if (el.classList.contains('console-error-level')) type = 'error';
                        else if (el.classList.contains('console-warning-level')) type = 'warning';
                        else if (el.classList.contains('console-info-level')) type = 'info';
                        else if (el.classList.contains('console-verbose-level')) type = 'verbose';
                        
                        return {
                            type: type,
                            message: el.querySelector('.console-message-text').textContent,
                            timestamp: el.querySelector('.console-message-timestamp')?.textContent || ''
                        };
                    });
                return logs;
                """
        elif panel == "network":
            if log_type == "errors":
                script = """
                const logs = Array.from(document.querySelectorAll('.network-item'))
                    .filter(el => {
                        const statusCell = el.querySelector('.status-column');
                        const statusCode = parseInt(statusCell?.textContent || '0');
                        return statusCode >= 400;
                    })
                    .map(el => {
                        return {
                            url: el.querySelector('.name-column')?.textContent || '',
                            status: el.querySelector('.status-column')?.textContent || '',
                            method: el.querySelector('.method-column')?.textContent || '',
                            type: el.querySelector('.type-column')?.textContent || '',
                            size: el.querySelector('.size-column')?.textContent || '',
                            time: el.querySelector('.time-column')?.textContent || ''
                        };
                    });
                return logs;
                """
            else:
                script = """
                const logs = Array.from(document.querySelectorAll('.network-item'))
                    .map(el => {
                        return {
                            url: el.querySelector('.name-column')?.textContent || '',
                            status: el.querySelector('.status-column')?.textContent || '',
                            method: el.querySelector('.method-column')?.textContent || '',
                            type: el.querySelector('.type-column')?.textContent || '',
                            size: el.querySelector('.size-column')?.textContent || '',
                            time: el.querySelector('.time-column')?.textContent || ''
                        };
                    });
                return logs;
                """
        else:
            raise ValueError(f"Unsupported DevTools panel: {panel}")
        
        logs = driver_instance.execute_script(script)
        
        # Close DevTools window and switch back to original
        driver_instance.close()
        driver_instance.switch_to.window(original_window)
        
        return logs
        
    except Exception as e:
        logger.error(f"Error getting logs from {panel} panel: {str(e)}")
        
        # Try to recover by switching back to the original window
        try:
            # Make sure driver is still valid
            if driver is not None:
                # Check if the original window still exists
                if original_window in driver_instance.window_handles:
                    driver_instance.switch_to.window(original_window)
                # If not, switch to any available window
                elif driver_instance.window_handles:
                    driver_instance.switch_to.window(driver_instance.window_handles[0])
        except Exception as cleanup_error:
            logger.error(f"Error during cleanup after exception: {str(cleanup_error)}")
        
        # Re-raise the original exception
        raise

def navigate_to_url(url: str, timeout: int = 60) -> str:
    """Navigate to the specified URL"""
    global driver
    logger = logging.getLogger(__name__)
    
    # Ensure we have a valid driver
    ensure_valid_driver()
    
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
    logger = logging.getLogger(__name__)
    
    # Ensure we have a valid driver
    ensure_valid_driver()
    
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
    logger = logging.getLogger(__name__)
    
    # Ensure we have a valid driver
    ensure_valid_driver()
    
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

def get_console_errors() -> str:
    """Get console errors from Chrome DevTools"""
    global driver
    logger = logging.getLogger(__name__)
    
    # Ensure we have a valid driver
    try:
        ensure_valid_driver()
        logs = get_devtools_logs(panel="console", log_type="errors")
        return json.dumps(logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting console errors: {str(e)}")
        return f"Error getting console errors: {str(e)}"

def get_console_logs() -> str:
    """Get console logs from Chrome DevTools"""
    global driver
    logger = logging.getLogger(__name__)
    
    # Ensure we have a valid driver
    try:
        ensure_valid_driver()
        logs = get_devtools_logs(panel="console")
        return json.dumps(logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting console logs: {str(e)}")
        return f"Error getting console logs: {str(e)}"

def get_network_logs() -> str:
    """Get network logs from Chrome DevTools"""
    global driver
    logger = logging.getLogger(__name__)
    
    try:
        ensure_valid_driver()
        logs = get_devtools_logs(panel="network")
        return json.dumps(logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting network logs: {str(e)}")
        return f"Error getting network logs: {str(e)}"

def get_network_errors() -> str:
    """Get network errors from Chrome DevTools"""
    global driver
    logger = logging.getLogger(__name__)
    
    try:
        ensure_valid_driver()
        logs = get_devtools_logs(panel="network", log_type="errors")
        return json.dumps(logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting network errors: {str(e)}")
        return f"Error getting network errors: {str(e)}"

async def serve(browser: str, headless: bool) -> None:
    """Main server function"""
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize the WebDriver - only Chrome is supported
        if browser.lower() != "chrome":
            logger.warning(f"Browser {browser} is not supported, defaulting to Chrome")
            browser = "chrome"
            
        logger.info(f"Checking for Chrome instance at 127.0.0.1:9222")
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
                Tool(
                    name=SeleniumTools.GET_CONSOLE_LOGS,
                    description="Get console logs from Chrome DevTools",
                    inputSchema=GetConsoleLogs.schema(),
                ),
                Tool(
                    name=SeleniumTools.GET_CONSOLE_ERRORS,
                    description="Get console errors from Chrome DevTools",
                    inputSchema=GetConsoleErrors.schema(),
                ),
                Tool(
                    name=SeleniumTools.GET_NETWORK_LOGS,
                    description="Get network logs from Chrome DevTools",
                    inputSchema=GetNetworkLogs.schema(),
                ),
                Tool(
                    name=SeleniumTools.GET_NETWORK_ERRORS,
                    description="Get network errors from Chrome DevTools",
                    inputSchema=GetNetworkErrors.schema(),
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
                
                elif name == SeleniumTools.GET_CONSOLE_LOGS:
                    result = get_console_logs()
                    return [TextContent(type="text", text=result)]
                
                elif name == SeleniumTools.GET_CONSOLE_ERRORS:
                    result = get_console_errors()
                    return [TextContent(type="text", text=result)]
                
                elif name == SeleniumTools.GET_NETWORK_LOGS:
                    result = get_network_logs()
                    return [TextContent(type="text", text=result)]
                
                elif name == SeleniumTools.GET_NETWORK_ERRORS:
                    result = get_network_errors()
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