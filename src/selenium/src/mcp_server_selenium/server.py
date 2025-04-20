import logging
from pathlib import Path
from typing import Optional
from enum import Enum
import os
import time
from datetime import datetime

from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions

# Define the data models for our tools
class Navigate(BaseModel):
    url: str

class TakeScreenshot(BaseModel):
    filename: Optional[str] = None

class SeleniumTools(str, Enum):
    NAVIGATE = "navigate"
    TAKE_SCREENSHOT = "take_screenshot"

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
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    elif browser.lower() == "firefox":
        options = FirefoxOptions()
        if headless:
            options.add_argument("--headless")
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
    else:
        raise ValueError(f"Unsupported browser: {browser}")
    
    # Set default window size
    driver.set_window_size(1366, 768)
    
    return driver

def navigate_to_url(url: str) -> str:
    """Navigate to the specified URL"""
    global driver
    if driver is None:
        raise RuntimeError("WebDriver is not initialized")
    
    driver.get(url)
    return f"Successfully navigated to {url}"

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

async def serve(browser: str, headless: bool) -> None:
    """Main server function"""
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize the WebDriver
        logger.info(f"Initializing {browser} WebDriver (headless: {headless})")
        initialize_driver(browser, headless)
        
        # Create the MCP server
        server = Server("mcp-selenium")
        
        @server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name=SeleniumTools.NAVIGATE,
                    description="Navigate to a specified URL",
                    inputSchema=Navigate.schema(),
                ),
                Tool(
                    name=SeleniumTools.TAKE_SCREENSHOT,
                    description="Take a screenshot of the current page",
                    inputSchema=TakeScreenshot.schema(),
                ),
            ]
        
        @server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            logger.info(f"Calling tool: {name} with arguments: {arguments}")
            
            try:
                if name == SeleniumTools.NAVIGATE:
                    args = Navigate(**arguments)
                    result = navigate_to_url(args.url)
                    return [TextContent(content=result)]
                
                elif name == SeleniumTools.TAKE_SCREENSHOT:
                    args = TakeScreenshot(**arguments)
                    result = take_screenshot(args.filename)
                    return [TextContent(content=result)]
                
                else:
                    return [TextContent(content=f"Unknown tool: {name}")]
            
            except Exception as e:
                logger.error(f"Error calling tool {name}: {str(e)}")
                return [TextContent(content=f"Error: {str(e)}")]
        
        # Start the server
        logger.info("Starting MCP Selenium server")
        await server.serve_stdio()
        
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
    
    finally:
        # Clean up the WebDriver when done
        if driver is not None:
            logger.info("Closing WebDriver")
            driver.quit() 