# Standard library imports
import logging
import time
import socket
import subprocess
import json
from datetime import datetime
from enum import Enum
from logging.config import dictConfig
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

# Third-party imports
import click
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

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
driver: Optional[webdriver.Chrome] = None

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

class GetConsoleLogs(BaseModel):
    pass

class GetConsoleErrors(BaseModel):
    pass

class GetNetworkLogs(BaseModel):
    pass

class GetNetworkErrors(BaseModel):
    pass

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
            "--no-default-browser-check",
            "--start-maximized",  # Start Chrome maximized
            "--auto-open-devtools-for-tabs"  # Auto-open DevTools for new tabs
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

def initialize_driver(browser: str = "chrome", headless: bool = False) -> webdriver.Chrome:
    """Initialize and return a WebDriver instance based on browser choice"""
    global driver
    
    if browser.lower() != "chrome":
        raise ValueError(f"Unsupported browser: {browser}. Only Chrome is supported.")
    
    # Check if Chrome is already running with remote debugging
    if not check_chrome_debugger_port():
        logger.info("Chrome not detected on port 9222, attempting to start a new instance")
        
        # Start Chrome with DevTools auto-open
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_data_dir = f"/tmp/chrome-debug-{timestamp}"
        
        logger.info(f"Starting Chrome with debugging port 9222 and user data dir {user_data_dir}")
        
        # Start Chrome as a subprocess with DevTools auto-open
        cmd = [
            "google-chrome-stable",
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--enable-logging",  # Enable logging
            "--start-maximized",  # Start Chrome maximized
            "--auto-open-devtools-for-tabs"  # Auto-open DevTools for new tabs
        ]
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            start_new_session=True  # Detach from the parent process
        )
        
        # Wait a moment for Chrome to start
        time.sleep(3)
        
        if not check_chrome_debugger_port():
            raise RuntimeError("Failed to start Chrome browser")
    else:
        logger.info("Chrome already running with remote debugging port 9222")
    
    # Setup capabilities to enable browser logging
    options = ChromeOptions()
    options.debugger_address = "127.0.0.1:9222"
    
    # Set logging preferences for both browser logs and performance logs
    options.set_capability('goog:loggingPrefs', {
        'browser': 'ALL',
        'performance': 'ALL'
    })
    
    # Create the driver
    driver = webdriver.Chrome(options=options)
    
    # Maximize the window
    driver.maximize_window()
    
    # Set longer page load timeout
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    
    return driver

def open_devtools_and_wait(panel: str) -> None:
    """Open Chrome DevTools and switch to specified panel"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
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

def get_devtools_logs(panel: str, log_type: str = "all") -> List[Dict[str, Any]]:
    """Get logs from DevTools panel"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    try:
        # Open DevTools with specified panel
        open_devtools_and_wait(panel)
        
        # Find DevTools window
        devtools_window = None
        original_window = driver.current_window_handle
        for window_handle in driver.window_handles:
            if window_handle != original_window:
                devtools_window = window_handle
                break
        
        if not devtools_window:
            raise RuntimeError("DevTools window not found")
        
        # Switch to DevTools window
        driver.switch_to.window(devtools_window)
        
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
        
        logs = driver.execute_script(script)
        
        # Close DevTools window and switch back to original
        driver.close()
        driver.switch_to.window(original_window)
        
        return logs
        
    except Exception as e:
        logger.error(f"Error getting logs from {panel} panel: {str(e)}")
        # Make sure we're back on the original window
        for window_handle in driver.window_handles:
            if window_handle == original_window:
                driver.switch_to.window(original_window)
                break
        raise

def get_browser_logs(driver: webdriver.Chrome, log_type='browser'):
    """Get logs from the browser and format them"""
    if driver is None:
        return []
    
    logs = []
    try:
        browser_logs = driver.get_log(log_type)
        for entry in browser_logs:
            logs.append({
                'type': entry.get('level', 'INFO').lower(),
                'message': entry.get('message', ''),
                'timestamp': entry.get('timestamp', 0)
            })
    except Exception as e:
        logger.error(f"Error getting browser logs: {str(e)}")
    
    return logs

def process_performance_log_entry(entry):
    """Process a performance log entry to extract the message"""
    try:
        return json.loads(entry['message'])['message']
    except Exception as e:
        logger.error(f"Error processing performance log entry: {str(e)}")
        return None

def get_network_logs_from_performance(driver: webdriver.Chrome):
    """Get network logs using performance logging"""
    if driver is None:
        return []
    
    try:
        # Get raw performance logs
        performance_logs = driver.get_log('performance')
        
        # Process the logs to extract the message part
        events = []
        for entry in performance_logs:
            event = process_performance_log_entry(entry)
            if event is not None:
                events.append(event)
        
        # Filter for network events
        network_events = []
        for event in events:
            if 'Network.' in event.get('method', ''):
                # Extract the relevant information
                method = event.get('method', '')
                params = event.get('params', {})
                request_id = params.get('requestId', '')
                
                # Create a simplified event object
                if method == 'Network.requestWillBeSent':
                    request = params.get('request', {})
                    network_events.append({
                        'type': 'request',
                        'requestId': request_id,
                        'method': request.get('method', ''),
                        'url': request.get('url', ''),
                        'timestamp': params.get('timestamp', 0),
                        'headers': request.get('headers', {})
                    })
                elif method == 'Network.responseReceived':
                    response = params.get('response', {})
                    status = response.get('status', 0)
                    status_text = response.get('statusText', '')
                    
                    network_events.append({
                        'type': 'response',
                        'requestId': request_id,
                        'status': status,
                        'statusText': status_text,
                        'url': response.get('url', ''),
                        'timestamp': params.get('timestamp', 0),
                        'headers': response.get('headers', {}),
                        'mimeType': response.get('mimeType', ''),
                        'hasError': status >= 400
                    })
                elif method == 'Network.loadingFailed':
                    error_text = params.get('errorText', '')
                    canceled = params.get('canceled', False)
                    
                    network_events.append({
                        'type': 'failed',
                        'requestId': request_id,
                        'errorText': error_text,
                        'canceled': canceled,
                        'timestamp': params.get('timestamp', 0),
                        'hasError': True
                    })
        
        return network_events
    except Exception as e:
        logger.error(f"Error getting network logs from performance: {str(e)}")
        return []

def get_response_body(driver: webdriver.Chrome, request_id: str):
    """Get the response body for a specific request using CDP command"""
    if driver is None:
        return None
    
    try:
        result = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
        return result
    except Exception as e:
        logger.error(f"Error getting response body: {str(e)}")
        return None

@mcp.tool()
def selenium_navigate(url: str, timeout: int = 60) -> str:
    """Navigate to a specified URL with configurable timeout"""
    global driver
    if driver is None:
        logger.info("WebDriver is not initialized, initializing now...")
        try:
            driver = initialize_driver()
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise RuntimeError(f"Failed to initialize WebDriver: {str(e)}")
    
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
        error_msg = str(e)
        logger.error(f"Error after {elapsed:.2f} seconds while navigating to {url}: {error_msg}")
        
        # Check if the error is due to the browser being closed
        if "invalid session id" in error_msg and "browser has closed" in error_msg:
            logger.info("Detected that Chrome has been closed. Attempting to restart Chrome...")
            
            # Attempt to restart Chrome
            if start_chrome():
                logger.info("Successfully restarted Chrome")
                
                # Reinitialize the driver
                try:
                    driver = initialize_driver()
                    logger.info("WebDriver reinitialized successfully")
                    
                    # Try to navigate again
                    try:
                        driver.get(url)
                        return f"Chrome was restarted and navigation to {url} initiated"
                    except Exception as nav_e:
                        return f"Chrome was restarted but navigation failed: {str(nav_e)}"
                except Exception as init_e:
                    return f"Chrome was restarted but failed to reinitialize WebDriver: {str(init_e)}"
            else:
                return f"Failed to restart Chrome after it was closed"
        
        # For other errors, just raise the exception
        raise Exception(f"Error navigating to {url}: {error_msg}")

@mcp.tool()
def selenium_take_screenshot() -> str:
    """Take a screenshot of the current page"""
    global driver
    if driver is None:
        logger.info("WebDriver is not initialized, initializing now...")
        try:
            driver = initialize_driver()
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise RuntimeError(f"Failed to initialize WebDriver: {str(e)}")
    
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
        logger.info("WebDriver is not initialized, initializing now...")
        try:
            driver = initialize_driver()
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise RuntimeError(f"Failed to initialize WebDriver: {str(e)}")
    
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

@mcp.tool()
def selenium_get_console_logs() -> str:
    """Get console logs from browser"""
    global driver
    if driver is None:
        logger.info("WebDriver is not initialized, initializing now...")
        try:
            driver = initialize_driver()
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            return f"Failed to initialize WebDriver: {str(e)}"
    
    try:
        # Force some console messages for testing
        # driver.execute_script("""
        #     console.log('Test log message');
        #     console.info('Test info message');
        #     console.warn('Test warning message');
        #     console.error('Test error message');
        # """)
        
        # Get browser logs
        logs = get_browser_logs(driver)
        
        return json.dumps(logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting console logs: {str(e)}")
        return f"Error getting console logs: {str(e)}"

@mcp.tool()
def selenium_get_console_errors() -> str:
    """Get console errors from browser"""
    global driver
    if driver is None:
        logger.info("WebDriver is not initialized, initializing now...")
        try:
            driver = initialize_driver()
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            return f"Failed to initialize WebDriver: {str(e)}"
    
    try:
        # Force some console messages for testing
        # driver.execute_script("""
        #     console.log('Test log message');
        #     console.info('Test info message');
        #     console.warn('Test warning message');
        #     console.error('Test error message');
        # """)

        # Get all logs
        all_logs = get_browser_logs(driver)
        
        # Filter for errors only - include SEVERE, ERROR levels
        error_logs = [log for log in all_logs if log['type'].upper() in ('SEVERE', 'ERROR')]
        
        return json.dumps(error_logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting console errors: {str(e)}")
        return f"Error getting console errors: {str(e)}"

@mcp.tool()
def selenium_get_network_logs() -> str:
    """Get network logs from browser performance data"""
    global driver
    if driver is None:
        logger.info("WebDriver is not initialized, initializing now...")
        try:
            driver = initialize_driver()
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            return f"Failed to initialize WebDriver: {str(e)}"
    
    try:
        # Get network logs from performance data
        network_logs = get_network_logs_from_performance(driver)
        
        # Return formatted logs
        return json.dumps(network_logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting network logs: {str(e)}")
        return f"Error getting network logs: {str(e)}"

@mcp.tool()
def selenium_get_network_errors() -> str:
    """Get network errors from browser performance data"""
    global driver
    if driver is None:
        logger.info("WebDriver is not initialized, initializing now...")
        try:
            driver = initialize_driver()
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            return f"Failed to initialize WebDriver: {str(e)}"
    
    try:
        # Get all network logs
        all_logs = get_network_logs_from_performance(driver)
        
        # Filter for errors only (status >= 400 or failed requests)
        error_logs = [log for log in all_logs if log.get('hasError', False)]
        
        return json.dumps(error_logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting network errors: {str(e)}")
        return f"Error getting network errors: {str(e)}"

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