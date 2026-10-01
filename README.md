# recon-draft

An AI-powered bank reconciliation assistant.

## Requirements

- Python 3.11+

## Virtual Environment Setup

### 1. Create a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
```

**macOS / Linux:**
```bash
python3 -m venv venv
```

### 2. Activate the Virtual Environment

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```
*(If script execution is restricted on Windows, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

**Windows (Command Prompt):**
```cmd
venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configuration

Copy the example environment file and configure your API key and model:

```bash
cp .env.example .env
```

Edit `.env` and set:
- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `CLAUDE_MODEL`: Claude model name (e.g. `claude-3-5-sonnet-20241022`)
