# Selenium MCP Server

A Model Context Protocol (MCP) server that provides tools for controlling Selenium WebDriver programmatically via LLMs.

## Features

- Navigate to URLs
- Take screenshots of web pages

## Installation

1. Clone the repository
2. Create a virtual environment
3. Install the package

```bash
# Clone the repository (not needed if you already have the code)
git clone <repository-url>
cd mcp-server-selenium

# Create a virtual environment and install the package
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

### Using the run script

The easiest way to start the server is to use the provided run script:

```bash
./run.sh
```

You can pass command-line arguments to the script:

```bash
./run.sh --browser firefox --headless
```

### Manual start

Alternatively, you can start the server manually:

```bash
python -m mcp_server_selenium --browser chrome --headless
```

### Command-line options

- `--browser`, `-b`: Browser to use (chrome, firefox). Default is chrome.
- `--headless`: Run browser in headless mode. Default is false.
- `--verbose`, `-v`: Increase verbosity. Can be repeated for more verbosity.

## Available Tools

### Navigate

Navigates to a specified URL.

Parameters:
- `url`: The URL to navigate to

Example:
```json
{
  "url": "https://www.example.com"
}
```

### Take Screenshot

Takes a screenshot of the current page.

Parameters:
- `filename` (optional): Name of the screenshot file. If not provided, a timestamp will be used.

Example:
```json
{
  "filename": "example_homepage"
}
```

Screenshots are saved in `~/selenium-mcp/screenshot/` directory.

## License

MIT 