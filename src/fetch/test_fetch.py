#!/usr/bin/env python

# Simple test to verify the fetch module components can be loaded
import sys
import os

# Add the mcp_server_fetch module to the Python path
module_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.insert(0, module_path)

print("Starting fetch module test...")
print(f"Added module path: {module_path}")

try:
    from mcp_server_fetch.server import (
        DEFAULT_USER_AGENT_AUTONOMOUS,
        extract_content_from_html,
        get_robots_txt_url,
        fetch_url,
        serve
    )
    print("Successfully imported server components")
    
    # Test basic functions
    print("Testing get_robots_txt_url...")
    robots_url = get_robots_txt_url("https://www.google.com")
    print(f"Robots URL: {robots_url}")
    
    print("All imports successful!")
except ImportError as e:
    print(f"Import Error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")

print("Test completed") 