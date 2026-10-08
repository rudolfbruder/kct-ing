"""Application entrypoint.

Run in the Jupyter terminal (8080 is taken by JupyterLab itself):

    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
from fastapi import FastAPI

from routes.api import router

app = FastAPI(
    title="KCT — Key Control Testing",
    version="0.1.0",
    description="Stage 1: summarization of control details and test plans.",
)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"service": "kct", "docs": "/docs", "api": "/api/v1/health"}
