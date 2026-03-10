# Doppler + Railway Setup

Pattern for using Doppler as the single source of truth for secrets, with Railway as the deployment platform.

## Overview

Instead of managing env vars in Railway directly, we:
1. Store all secrets in Doppler
2. Set only `DOPPLER_TOKEN` in Railway
3. Use `doppler run --` in the Docker CMD to inject secrets at runtime

**Benefits:**
- Single source of truth for secrets
- Easy secret rotation (update Doppler, redeploy)
- No secrets scattered across Railway dashboard
- Same secrets work locally via `doppler run --`

## Setup Steps

### 1. Doppler Project Setup

1. Create a Doppler project at https://dashboard.doppler.com
2. Create configs for each environment (e.g., `dev`, `stg`, `prd`)
3. Add all your env vars to the appropriate config

### 2. Create Service Token

1. In Doppler, go to your project → config (e.g., `prd`)
2. Click "Service Tokens" → "Generate"
3. Name it something like `railway-prd`
4. Copy the token (you won't see it again)

### 3. Dockerfile

Install Doppler CLI and wrap your app command:

```dockerfile
FROM python:3.12-slim

# Install Doppler CLI
RUN apt-get update && apt-get install -y apt-transport-https ca-certificates curl gnupg && \
    curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" > /etc/apt/sources.list.d/doppler-cli.list && \
    apt-get update && apt-get install -y doppler && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# doppler run -- injects all env vars from Doppler at runtime
CMD ["doppler", "run", "--", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

For Node.js:
```dockerfile
FROM node:20-slim

# Install Doppler CLI
RUN apt-get update && apt-get install -y apt-transport-https ca-certificates curl gnupg && \
    curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" > /etc/apt/sources.list.d/doppler-cli.list && \
    apt-get update && apt-get install -y doppler && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

EXPOSE 3000

CMD ["doppler", "run", "--", "node", "dist/index.js"]
```

### 4. railway.toml

Tell Railway to use your Dockerfile:

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### 5. Railway Configuration

1. In Railway, go to your service → Variables
2. Add ONE variable: `DOPPLER_TOKEN` = (paste the service token from step 2)
3. Deploy

That's it. Railway builds the Docker image, and at runtime `doppler run --` fetches and injects all secrets.

## Local Development

### First-time setup

```bash
# Install Doppler CLI
brew install dopplerhq/cli/doppler

# Login to Doppler
doppler login

# Setup project (run in repo root)
doppler setup
# Select your project and config (e.g., dev)
```

### Running locally

```bash
# Python
doppler run -- uvicorn app.main:app --reload

# Node.js
doppler run -- npm run dev

# Run tests
doppler run -- pytest
doppler run -- npm test
```

## .env.example

Keep an `.env.example` file listing all required vars (without values) for documentation:

```bash
# Core
DATABASE_URL=
API_URL=

# Auth
JWT_SECRET=
INTERNAL_API_KEY=

# Provider keys
SOME_API_KEY=
ANOTHER_API_KEY=
```

## Troubleshooting

### "DOPPLER_TOKEN not set"
- Verify the token is set in Railway Variables
- Redeploy the service

### "Invalid token"
- Token may have been revoked — generate a new one in Doppler
- Make sure you're using a Service Token, not a Personal Token

### Secrets not updating after Doppler change
- Railway caches the Docker image
- Trigger a redeploy: `railway up` or push a commit

### Testing Doppler locally
```bash
# Verify you're connected to the right project/config
doppler secrets

# See what would be injected
doppler run -- printenv | grep YOUR_VAR
```

## Multiple Environments

For staging/production separation:

1. Create separate configs in Doppler (`stg`, `prd`)
2. Generate a service token for each
3. In Railway, create separate services or use environment-specific variables
4. Set the appropriate `DOPPLER_TOKEN` for each

## Security Notes

- Service tokens are scoped to a single project + config
- Rotate tokens periodically via Doppler dashboard
- Never commit `DOPPLER_TOKEN` to git
- Use Doppler's audit log to track secret access
