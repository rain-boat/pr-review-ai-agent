# PR Review Agent — Setup

## 1. Run the Project

**Terminal 1 — FastAPI**

```bash
cd /Users/meena/Documents/backend/fast_api/pr_review
source /Users/meena/Documents/backend/fast_api/learning/myenv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — ngrok**

```bash
ngrok http 8000
```

Note:- To check server execute below command in other terminal
curl http://127.0.0.1:8000/health
## 2. Configure GitHub App

1. Open your GitHub App settings.
2. Enable webhook delivery and set the webhook URL to(Developer options -> create app):

   `https://YOUR_NGROK_URL/webhooks/github`

3. Enable the **Pull requests** webhook event.
4. Set repository permissions:

   - Contents: Read-only
   - Metadata: Read-only
   - Pull requests: Read and write
   - Checks: Read and write

5. Install the GitHub App on your target repository.
6. Ensure the `.env` file contains your GitHub App ID, installation ID, Gemini API key, and PostgreSQL database URL.
7. Keep `github-app.pem` in the configured private-key location.

## 3. Verify the Server

Open:

- Health check: http://127.0.0.1:8000/health
- API documentation: http://127.0.0.1:8000/docs

## 4. Test Automatic Review

Open a pull request or push a new commit to an existing pull request in the configured repository.

The agent should review the changes, post new inline comments, and update the GitHub Check Run.

**Important:** The ngrok URL may change when ngrok restarts. Update the GitHub webhook URL if it changes. Never commit `.env` or `github-app.pem` to GitHub.

