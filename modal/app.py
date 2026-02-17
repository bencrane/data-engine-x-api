import os

import modal
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

app = modal.App("data-engine-x-micro")

image = modal.Image.debian_slim().pip_install("fastapi", "httpx")
auth_scheme = HTTPBearer(auto_error=False)


def require_internal_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
) -> None:
    expected_key = os.environ.get("MODAL_INTERNAL_AUTH_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MODAL_INTERNAL_AUTH_KEY is not configured",
        )

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or credentials.credentials != expected_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


web_app = FastAPI(
    title="data-engine-x-micro",
    dependencies=[Depends(require_internal_auth)],
)


@web_app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("parallel-ai"),
        modal.Secret.from_name("internal-auth"),
    ],
)
@modal.asgi_app()
def fastapi_app() -> FastAPI:
    return web_app
