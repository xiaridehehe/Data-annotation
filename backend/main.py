"""Production API entry point for the relational annotation application.

The original records-based DICOM upload and annotation routes have deliberately
been removed. Images stay in the browser; the server exposes only authentication,
the relational workspace API, and the review workflow.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend import auth, relational_api, workflow
from backend.database import create_database_engine


engine = create_database_engine()

auth.engine = engine
relational_api.engine = engine
workflow.engine = engine

app = FastAPI(title="Knee MRI Annotation")
app.include_router(auth.router)
app.include_router(auth.admin_router)
app.include_router(relational_api.router)
app.include_router(workflow.router)


@app.middleware("http")
async def authenticate_api(request, call_next):
    """Protect every non-login API path, including unknown or retired routes."""
    if (
        request.url.path.startswith("/api/")
        and request.method != "OPTIONS"
        and request.url.path
        not in {"/api/auth/register", "/api/auth/login", "/api/auth/logout"}
    ):
        try:
            await run_in_threadpool(auth.require_user, request)
        except HTTPException as error:
            return JSONResponse({"detail": error.detail}, status_code=error.status_code)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
