import logging
from pathlib import Path
from typing import Optional
from enum import Enum
import os
import time
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions

# Define the data models for our tools
class Navigate(BaseModel):
    url: str
    timeout: int = Field(default=60, description="Timeout in seconds for page load")

class TakeScreenshot(BaseModel):
    filename: Optional[str] = None

class CheckPageReady(BaseModel):
    wait_seconds: int = Field(default=0, description="Optional seconds to wait before checking")

class SeleniumTools(str, Enum):
    NAVIGATE = "navigate"
    TAKE_SCREENSHOT = "take_screenshot"
    CHECK_PAGE_READY = "check_page_ready"

# Global variable to store WebDriver instance
driver = None

# Helper functions for Selenium operations
def initialize_driver(browser: str, headless: bool) -> webdriver.Remote:
    """Initialize and return a WebDriver instance based on browser choice"""
    global driver
    
    if browser.lower() == "chrome":
        options = ChromeOptions()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # Add option to disable timeouts
        options.add_argument("--disable-hang-monitor")
        options.add_argument("--disable-dev-shm-usage")
        # Increase page load timeout
        options.page_load_strategy = 'normal'
        
        # Use the specified ChromeDriver path instead of ChromeDriverManager
        chrome_driver_path = "/home/xuananh/Downloads/chromedriver-linux64/chromedriver"
        service = ChromeService(executable_path=chrome_driver_path)
        driver = webdriver.Chrome(service=service, options=options)
        
        # Set longer page load timeout (default is only 30 seconds)
        driver.set_page_load_timeout(120)
        driver.set_script_timeout(120)
    elif browser.lower() == "firefox":
        options = FirefoxOptions()
        if headless:
            options.add_argument("--headless")
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
        driver.set_page_load_timeout(120)
        driver.set_script_timeout(120)
    else:
        raise ValueError(f"Unsupported browser: {browser}")
    
    # Set default window size
    driver.set_window_size(1366, 768)
    
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
            return f"Navigation to {url} started but timed out after {navigation_timeout} seconds. Current URL: {current_url}"
        else:
            return f"Navigation to {url} timed out after {navigation_timeout} seconds, but may continue loading"
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error after {elapsed:.2f} seconds while navigating to {url}: {str(e)}")
        raise Exception(f"Error navigating to {url}: {str(e)}")

def take_screenshot(filename: Optional[str] = None) -> str:
    """Take a screenshot of the current page"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    # Create the screenshot directory if it doesn't exist
    screenshot_dir = Path.home() / "selenium-mcp" / "screenshot"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate a filename if not provided
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
    elif not filename.endswith(('.png', '.jpg', '.jpeg')):
        filename = f"{filename}.png"
    
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
        # Initialize the WebDriver
        logger.info(f"Initializing {browser} WebDriver (headless: {headless})")
        initialize_driver(browser, headless)
        
        # Create the MCP server with increased timeout
        server = Server("mcp-selenium")
        
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
                    args = Navigate(**arguments)
                    # Ensure a reasonable timeout to avoid MCP timeout
                    if args.timeout > 20:
                        logger.info(f"Reducing timeout from {args.timeout} to 20 seconds to avoid MCP timeout")
                        args.timeout = 20
                    result = navigate_to_url(args.url, args.timeout)
                    return [TextContent(type="text", text=result)]
                
                elif name == SeleniumTools.TAKE_SCREENSHOT:
                    # Handle potentially nested structure in arguments
                    if isinstance(arguments.get('filename'), dict) and 'filename' in arguments['filename']:
                        # Extract the inner filename value
                        filename_arg = arguments['filename']['filename']
                        args = TakeScreenshot(filename=filename_arg)
                    else:
                        # Normal case
                        args = TakeScreenshot(**arguments)
                    
                    result = take_screenshot(args.filename)
                    return [TextContent(type="text", text=result)]
                
                elif name == SeleniumTools.CHECK_PAGE_READY:
                    args = CheckPageReady(**arguments)
                    result = check_page_ready(args.wait_seconds)
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
        # Clean up the WebDriver when done
        if driver is not None:
            logger.info("Closing WebDriver")
            driver.quit() 