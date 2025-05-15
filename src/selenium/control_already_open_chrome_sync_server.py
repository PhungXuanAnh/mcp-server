# Standard library imports
import json
import logging
import socket
import subprocess
import time
from datetime import datetime
from enum import Enum
from logging.config import dictConfig
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Third-party imports
import click
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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
            "filename": "/tmp/selenium-mcp.log",
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
     filter_url_by_text: str = Field(default='', description="Optional string to filter the network logs by url")
    

class GetNetworkErrors(BaseModel):
    filter_url_by_text: str = Field(default='', description="Optional string to filter the network logs by url")

class ClickElement(BaseModel):
    text: Optional[str] = Field(default=None, description="Text content of the element to click")
    class_name: Optional[str] = Field(default=None, description="Class name of the element to click")
    id: Optional[str] = Field(default=None, description="ID of the element to click")

class LocalStorageAdd(BaseModel):
    key: str = Field(description="Key for the local storage item")
    string_value: str = Field(default='', description="String value to store in local storage")
    object_value: Dict[str, Any] = Field(default_factory=dict, description="Object value to store in local storage as JSON")
    create_empty_string: bool = Field(default=False, description="Whether to create an empty string value if string_value is empty")
    create_empty_object: bool = Field(default=False, description="Whether to create an empty object value if object_value is empty")

class LocalStorageRead(BaseModel):
    key: str = Field(description="Key of the local storage item to read")

class LocalStorageRemove(BaseModel):
    key: str = Field(description="Key of the local storage item to remove")

class LocalStorageReadAll(BaseModel):
    pass

class LocalStorageRemoveAll(BaseModel):
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

def get_network_logs_from_performance(driver: webdriver.Chrome, filter_url_by_text: str = ''):
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
        
        # Group network events by requestId
        grouped_events: Dict[str, List[Dict[str, Any]]] = {}
        for event in network_events:
            request_id = event.get('requestId', '')
            if request_id not in grouped_events:
                grouped_events[request_id] = []
            grouped_events[request_id].append(event)
        
        # Filter by URL domain text if specified
        if filter_url_by_text:
            logger.info(f"Filtering network logs by domain containing: {filter_url_by_text}")
            filtered_events = {}
            for request_id, events_list in grouped_events.items():
                # Check if any event in this group has a URL domain containing the filter text
                for event in events_list:
                    if 'url' in event:
                        try:
                            domain = urlparse(event['url']).netloc
                            if filter_url_by_text in domain:
                                filtered_events[request_id] = events_list
                                break
                        except Exception as e:
                            logger.error(f"Error parsing URL domain: {str(e)}")
            grouped_events = filtered_events
        
        # Convert dictionary to list of lists
        result = list(grouped_events.values())
        
        return result
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
def navigate(url: str, timeout: int = 60) -> str:
    """Navigate to a specified URL with the Chrome browser.
    
    This tool navigates the browser to the provided URL. If the URL doesn't start with 
    http:// or https://, https:// will be added automatically.
    
    Args:
        url: The URL to navigate to. Will add https:// if protocol is missing.
        timeout: Maximum time in seconds to wait for the navigation to complete.
            Default is 60 seconds.
    
    Returns:
        A message confirming navigation started or reporting any issues.
    """
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
            return f"Navigation to {url} started but timed out after {navigation_timeout} seconds. You can use check_page_ready tool to check if the page is loaded. Current URL: {current_url}"
        else:
            return f"Navigation to {url} timed out after {navigation_timeout} seconds, but may continue loading. You can use check_page_ready tool to check if the page is loaded. Current URL: {current_url}"
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
def take_screenshot() -> str:
    """Take a screenshot of the current browser window.
    
    This tool captures the current visible area of the browser window and saves it
    as a PNG file in the ~/selenium-mcp/screenshot directory. The filename will include
    a timestamp for uniqueness.
    
    Returns:
        The path to the saved screenshot file.
    """
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
def check_page_ready(wait_seconds: int = 0) -> str:
    """Check if the current page is fully loaded.
    
    This tool checks the document.readyState of the current page to determine if it has
    finished loading. It can optionally wait a specified number of seconds before checking.
    
    Args:
        wait_seconds: Number of seconds to wait before checking the page's ready state.
            Default is 0 (check immediately).
    
    Returns:
        A message indicating the current ready state of the page (complete, interactive, or loading).
    """
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
def get_console_logs() -> str:
    """Retrieve all console logs from the browser.
    
    This tool collects all console logs (info, warnings, errors) that have been output
    in the browser's JavaScript console since the page was loaded.
    
    Returns:
        A JSON string containing all console log entries, including their type and message.
    """
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
        # Get browser logs
        logs = get_browser_logs(driver)
        
        return json.dumps(logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting console logs: {str(e)}")
        return f"Error getting console logs: {str(e)}"

@mcp.tool()
def get_console_errors() -> str:
    """Retrieve only error messages from the browser console.
    
    This tool collects only SEVERE and ERROR level messages that have been output
    in the browser's JavaScript console, filtering out informational and warning messages.
    
    Returns:
        A JSON string containing only console error messages.
    """
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
        # Get all logs
        all_logs = get_browser_logs(driver)
        
        # Filter for errors only - include SEVERE, ERROR levels
        error_logs = [log for log in all_logs if log['type'].upper() in ('SEVERE', 'ERROR')]
        
        return json.dumps(error_logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting console errors: {str(e)}")
        return f"Error getting console errors: {str(e)}"

@mcp.tool()
def get_network_logs(filter_url_by_text: str = '') -> str:
    """Retrieve network request logs from the browser.
    
    This tool collects all network activity (requests and responses) that has occurred
    since the page was loaded. Results can optionally be filtered by domain.
    
    Args:
        filter_url_by_text: Text to filter domain names by. When specified, only network
            requests to domains containing this text will be included. Default is empty
            string (no filtering).
    
    Returns:
        A JSON string containing the network request logs, grouped by request ID.
    """
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
        network_logs = get_network_logs_from_performance(driver, filter_url_by_text)
        
        # Return formatted logs
        return json.dumps(network_logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting network logs: {str(e)}")
        return f"Error getting network logs: {str(e)}"

@mcp.tool()
def get_network_errors(filter_url_by_text: str = '') -> str:
    """Retrieve only failed network requests from the browser.
    
    This tool collects network activity with error status codes (4xx/5xx) or other
    network failures. Results can optionally be filtered by domain.
    
    Args:
        filter_url_by_text: Text to filter domain names by. When specified, only network
            errors from domains containing this text will be included. Default is empty
            string (no filtering).
    
    Returns:
        A JSON string containing only failed network requests, grouped by request ID.
    """
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
        all_logs = get_network_logs_from_performance(driver, filter_url_by_text)
        
        # Filter for errors only (status >= 400 or failed requests)
        error_logs = []
        for request_events in all_logs:
            # Check if any event in this request group has an error
            has_error = any(event.get('hasError', False) for event in request_events)
            if has_error:
                error_logs.append(request_events)
        
        return json.dumps(error_logs, indent=2)
    except Exception as e:
        logger.error(f"Error getting network errors: {str(e)}")
        return f"Error getting network errors: {str(e)}"

@mcp.tool()
def click_to_element(text: str = '', class_name: str = '', id: str = '') -> str:
    """Click on an element identified by text content, class name, or ID.
    
    This tool finds and clicks on an element based on specified criteria. At least one 
    of text, class_name, or id must be provided. If multiple elements match the criteria, 
    or if no elements are found, an error message is returned.
    
    Args:
        text: Text content of the element to click. Case-sensitive text matching.
        class_name: CSS class name of the element to click.
        id: ID attribute of the element to click.
    
    Returns:
        A message indicating whether the click was successful or an error message.
    """
    global driver
    if driver is None:
        logger.info("WebDriver is not initialized, initializing now...")
        try:
            driver = initialize_driver()
            logger.info("WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            return f"Failed to initialize WebDriver: {str(e)}"
    
    if text == '' and class_name == '' and id == '':
        return "Error: At least one of text, class_name, or id must be provided"
    
    try:
        elements = []
        
        # Build XPath conditions based on provided arguments
        conditions = []
        
        if id != '':
            conditions.append(f"@id='{id}'")
        
        if class_name != '':
            conditions.append(f"contains(@class, '{class_name}')")
        
        if text != '':
            conditions.append(f"contains(text(), '{text}')")
        
        # Combine conditions with 'and'
        xpath = "//*"
        if conditions:
            xpath += "[" + " and ".join(conditions) + "]"
        
        logger.info(f"Looking for elements with XPath: {xpath}")
        elements = driver.find_elements(By.XPATH, xpath)
        
        # Check if we found exactly one element
        if len(elements) == 0:
            criteria_str = []
            if text != '':
                criteria_str.append(f"text='{text}'")
            if class_name != '':
                criteria_str.append(f"class='{class_name}'")
            if id != '':
                criteria_str.append(f"id='{id}'")
            
            error_msg = f"No elements found matching criteria: {', '.join(criteria_str)}"
            logger.error(error_msg)
            return error_msg
        
        if len(elements) > 1:
            error_msg = f"Found {len(elements)} elements matching the criteria. Please provide more specific criteria."
            logger.error(error_msg)
            return error_msg
        
        # Get the element
        element = elements[0]
        
        # Store element properties BEFORE clicking
        # Using try-except for each property to handle potential issues
        try:
            tag_name = element.tag_name
        except:
            tag_name = "unknown"
            
        try:
            element_id = element.get_attribute("id") or "no-id"
        except:
            element_id = "unknown"
            
        try:
            element_class = element.get_attribute("class") or "no-class"
        except:
            element_class = "unknown"
            
        try:
            element_text = element.text[:50] + "..." if len(element.text) > 50 else element.text
        except:
            element_text = "unknown"
        
        # Store current URL before the click
        current_url = driver.current_url
        
        # Now click the element
        element.click()
        
        # Wait a moment for any navigation to start
        time.sleep(0.5)
        
        # Check if the URL has changed, indicating navigation occurred
        new_url = driver.current_url
        if new_url != current_url:
            return f"Successfully clicked on {tag_name} element which triggered navigation from {current_url} to {new_url}"
        
        # If no navigation occurred, return the standard success message
        return f"Successfully clicked on {tag_name} element with id='{element_id}', class='{element_class}', text='{element_text}'"
    
    except Exception as e:
        error_msg = f"Error clicking element: {str(e)}"
        logger.error(error_msg)
        
        # Check if navigation occurred despite the error
        try:
            new_url = driver.current_url
            if 'current_url' in locals() and new_url != current_url:
                return f"Click succeeded with navigation to {new_url}, but encountered error when reporting: {str(e)}"
        except:
            pass
            
        return error_msg

def is_json_string(value: str) -> bool:
    try:
        json.loads(value)
        return True
    except:
        return False

@mcp.tool()
def local_storage_add(key: str, string_value: str = '', object_value: dict = {}, create_empty_string: bool = False, create_empty_object: bool = False) -> str:
    """Add or update a key-value pair in browser's local storage.
    
    This tool adds a new key-value pair to the browser's localStorage, or updates
    the value if the key already exists.
    
    Args:
        key: The key name for the local storage item.
        string_value: The string value to store in local storage. Default is empty string.
        object_value: The object value to store in local storage as JSON. Default is empty dict.
                     When provided, this takes precedence over string_value.
        create_empty_string: Whether to create an empty string value if string_value is empty. Default is False.
        create_empty_object: Whether to create an empty object value if object_value is empty. Default is False.
    
    Returns:
        A message indicating whether the operation was successful.
    """
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
        # Determine the value to use
        if object_value or create_empty_object:
            # Convert the object to JSON string for storage
            json_value = json.dumps(object_value)
            # Need to properly escape quotes for JavaScript execution
            escaped_json = json_value.replace("'", "\\'").replace('"', '\\"')
            script = f"window.localStorage.setItem('{key}', JSON.stringify({json.dumps(object_value)}));"
        elif string_value or create_empty_string:
            # Check if string_value is a valid JSON string and handle accordingly
            try:
                # Try to parse as JSON to see if it's a JSON string
                json_obj = json.loads(string_value)
                # If it parses successfully, treat it as JSON
                script = f"window.localStorage.setItem('{key}', JSON.stringify({string_value}));"
            except json.JSONDecodeError:
                # Not valid JSON, treat as regular string
                script = f"window.localStorage.setItem('{key}', '{string_value}');"
        else:
            return f"No value provided for key '{key}'. Set create_empty_string or create_empty_object to True to create with empty value."
            
        driver.execute_script(script)
        logger.info("Ran script: %s", script)
        
        # Verify the item was added correctly
        verification_script = f"return window.localStorage.getItem('{key}');"
        stored_value = driver.execute_script(verification_script)
        
        return f"Successfully added key '{key}' to local storage with value: {stored_value}"
    
    except Exception as e:
        error_msg = f"Error adding to local storage: {str(e)}"
        logger.error(error_msg)
        return error_msg

@mcp.tool()
def local_storage_read(key: str) -> str:
    """Read a value from browser's local storage by key.
    
    This tool retrieves the value associated with the specified key from the browser's
    localStorage. If the key doesn't exist, it returns a message indicating the key was not found.
    
    Args:
        key: The key name of the local storage item to read.
    
    Returns:
        The value associated with the key, or a message if the key doesn't exist.
    """
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
        # Execute JavaScript to get the value from local storage
        script = f"return window.localStorage.getItem('{key}');"
        value = driver.execute_script(script)
        
        if value is None:
            return f"Key '{key}' not found in local storage"
        else:
            return f"Value for key '{key}': {value}"
    
    except Exception as e:
        error_msg = f"Error reading from local storage: {str(e)}"
        logger.error(error_msg)
        return error_msg

@mcp.tool()
def local_storage_remove(key: str) -> str:
    """Remove a key-value pair from browser's local storage.
    
    This tool removes the specified key and its associated value from the browser's
    localStorage. If the key doesn't exist, it returns a message indicating the key was not found.
    
    Args:
        key: The key name of the local storage item to remove.
    
    Returns:
        A message indicating whether the operation was successful.
    """
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
        # First check if the key exists
        check_script = f"return window.localStorage.getItem('{key}') !== null;"
        key_exists = driver.execute_script(check_script)
        
        if not key_exists:
            return f"Key '{key}' not found in local storage, nothing to remove"
        
        # Execute JavaScript to remove the item from local storage
        script = f"window.localStorage.removeItem('{key}');"
        driver.execute_script(script)
        
        # Verify the item was removed
        verification_script = f"return window.localStorage.getItem('{key}') === null;"
        was_removed = driver.execute_script(verification_script)
        
        if was_removed:
            return f"Successfully removed key '{key}' from local storage"
        else:
            return f"Error: Failed to remove key '{key}' from local storage"
    
    except Exception as e:
        error_msg = f"Error removing from local storage: {str(e)}"
        logger.error(error_msg)
        return error_msg

@mcp.tool()
def local_storage_read_all() -> str:
    """Read all key-value pairs from browser's local storage.
    
    This tool retrieves all items from the browser's localStorage and returns
    them as a dictionary. If localStorage is empty, it returns a message indicating
    that no items were found.
    
    Returns:
        A JSON string containing all localStorage items, or a message if localStorage is empty.
    """
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
        # Execute JavaScript to get all items from local storage
        script = """
        const items = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            items[key] = localStorage.getItem(key);
        }
        return items;
        """
        items = driver.execute_script(script)
        
        if not items:
            return "No items found in local storage"
        else:
            return json.dumps(items, indent=2)
    
    except Exception as e:
        error_msg = f"Error reading all items from local storage: {str(e)}"
        logger.error(error_msg)
        return error_msg

@mcp.tool()
def local_storage_remove_all() -> str:
    """Remove all key-value pairs from browser's local storage.
    
    This tool clears all items from the browser's localStorage. If localStorage
    is already empty, it returns a message indicating that there was nothing to remove.
    
    Returns:
        A message indicating whether the operation was successful.
    """
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
        # First check if there are any items in localStorage
        count_script = "return localStorage.length;"
        item_count = driver.execute_script(count_script)
        
        if item_count == 0:
            return "Local storage is already empty, nothing to remove"
        
        # Execute JavaScript to clear all items from local storage
        script = "localStorage.clear(); return localStorage.length === 0;"
        success = driver.execute_script(script)
        
        if success:
            return f"Successfully removed all {item_count} item(s) from local storage"
        else:
            return "Error: Failed to clear local storage"
    
    except Exception as e:
        error_msg = f"Error removing all items from local storage: {str(e)}"
        logger.error(error_msg)
        return error_msg

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