# Nova AI Chatbot

A Flask-based chatbot that uses Google's Gemini API to generate responses. The browser interface keeps conversation history for the current tab.

## Requirements

- Python 3.10 or later
- A Gemini API key

## Setup

Create and activate a virtual environment, then install the project dependencies.

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**macOS or Linux**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your Gemini API key:

```text
GEMINI_API_KEY=your-api-key
```

Keep `.env` private. It is excluded from Git.

## Run

Start the Flask development server:

```sh
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## Tests

Run the test suite from the project directory:

```sh
python -m unittest discover -s tests
```

## API

`POST /api/chat` accepts a JSON conversation and returns the assistant response:

```json
{
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}
```

The health endpoint is `GET /health`.

## Project layout

```text
app.py                 Flask routes and request validation
services/llm_service.py Gemini API integration
templates/index.html   Chat interface
static/                CSS and browser-side JavaScript
tests/                 Flask API tests
```