# Payments App - Agentic Python Project

An agentic Python application using Claude API for authentication and intelligent interactions.

## Setup Instructions

### 1. Prerequisites
- Python 3.8 or higher
- Claude API key (from https://console.anthropic.com/)

### 2. Installation

1. **Navigate to the project folder**
   ```bash
   cd "D:\PaymentsApp"
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**
   - On Windows:
     ```bash
     .\venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### 3. Configure Claude API Key

1. **Get your Claude API Key**
   - Go to https://console.anthropic.com/
   - Navigate to API keys
   - Create a new API key

2. **Set up .env file**
   - Edit the `.env` file in the project root
   - Replace `your_claude_api_key_here` with your actual API key:
     ```
     CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
     ```

3. **Verify Authentication**
   ```bash
   python src/main.py
   ```

## Project Structure

```
PaymentsApp/
├── config/
│   └── claude_auth.py      # Claude API authentication module
├── src/
│   └── main.py             # Main application entry point
├── .env                    # Environment variables (add your API key here)
├── .gitignore              # Git ignore rules
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Usage

### Basic Usage

```python
from config.claude_auth import authenticator

# Get the authenticated Claude client
client = authenticator.get_client()

# Use the client to interact with Claude API
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Your prompt here"}
    ]
)

print(response.content[0].text)
```

## VS Code Integration

### Setting up Claude Code in VS Code

1. **Install GitHub Copilot**
   - Open VS Code
   - Go to Extensions (Ctrl+Shift+X)
   - Search for "GitHub Copilot"
   - Install and sign in with your GitHub account

2. **Configure Python Interpreter**
   - Press Ctrl+Shift+P
   - Search for "Python: Select Interpreter"
   - Choose the interpreter from your virtual environment (venv)

3. **Use Claude Code**
   - Open the Chat view (Ctrl+Shift+I or Cmd+Shift+I)
   - Use `@workspace` to reference your project files
   - Ask Claude Code for help with your implementation

## API Authentication Flow

1. **Load Environment Variables**: `.env` file is loaded using `python-dotenv`
2. **Initialize Anthropic Client**: Create client with the API key
3. **Verify Authentication**: Test connection with a sample API call
4. **Use Client**: Make authenticated requests to Claude API

## Troubleshooting

### "CLAUDE_API_KEY not found in environment variables"
- Ensure `.env` file exists in the project root
- Check that `.env` has the correct format: `CLAUDE_API_KEY=your_key_here`
- Make sure there are no spaces around the `=` sign

### "Authentication failed"
- Verify your Claude API key is valid (check console.anthropic.com)
- Ensure you have active API quota
- Check network connectivity

## Next Steps

1. Implement your payment processing logic in `src/main.py`
2. Create additional modules for specific features
3. Add database integration as needed
4. Implement error handling and logging
5. Deploy to your hosting platform

## Support

For Claude API documentation, visit: https://docs.anthropic.com/
