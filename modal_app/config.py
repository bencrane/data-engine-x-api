# modal_app/config.py — Modal secrets, image definitions

import modal

# Define the Modal app
app = modal.App("data-engine-x")

# Define the base image with common dependencies
base_image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "httpx>=0.27.0",
    "pydantic>=2.6.0",
    "supabase>=2.3.0",
)

# Secrets for Modal functions
secrets = [
    modal.Secret.from_name("supabase-secrets"),
]
