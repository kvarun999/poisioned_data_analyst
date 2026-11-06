# Demo checklist for recording or presenting the project

## Before you start

- Confirm Python dependencies are installed.
- Confirm the project virtual environment is active.
- Confirm the app is ready to run.
- Confirm the `.env` file is present locally if needed.
- Make sure browser tabs are ready:
  - app homepage
  - health endpoint
  - API docs

## Run commands

### Terminal 1: Start the app

```bash
cd /home/battlebeast/Projects/Poisoned_Data_Analyst
DATABASE_URL=sqlite:///./poisoned_analyst.db uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### Optional: Check the live mode

```bash
curl http://localhost:8080/health
```

Expected output:

```json
{
  "status": "ok",
  "execution_mode": "live_celesto" or "local_fallback",
  "celesto_api_key_present": true,
  "celesto_sdk_available": true
}
```

## Browser navigation

### 1. Open the app homepage

- http://localhost:8080/

### 2. Open the health endpoint

- http://localhost:8080/health

### 3. Open the API docs

- http://localhost:8080/docs

### 4. Upload sample data

Use a small CSV such as:

```csv
name,value
alpha,10
beta,20
```

## Proof points to mention during the demo

- user uploads CSV through browser
- backend logs run metadata
- app checks for blocked or dangerous commands
- execution mode is disclosed at runtime
- result is summarized in structured JSON
- the architecture keeps the control plane and risky execution separate

## Good talking points

- This is a secure AI data-analysis sandbox.
- The risky analysis is isolated from the host environment.
- The app logs all commands and decisions.
- The system supports a live Celesto path when provisioned.
- The fallback strategy keeps the demo usable when live runtime is not active.

## What not to say

Do not claim that the cloud Celesto runtime is definitely active unless the provider has actually accepted the sandbox creation request. Instead, say:

> The project is ready for live Celesto execution, and it automatically falls back safely when the runtime is not available or not provisioned.

## Recording tips

- Keep the explanation short and confident.
- Open the browser at the homepage before starting the verbal explanation.
- Switch to the health endpoint to show runtime mode.
- Open the editor and point to [app/main.py](../app/main.py) as the execution engine.
- End by saying the design is practical, safety-aware, and suitable for AI-agent workflows.
