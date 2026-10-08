"""uvicorn main:app --host 0.0.0.0 --port 8000 --reload"""
from fastapi import FastAPI

from routes.api import router

app = FastAPI(title="KCT", version="0.1.0")
app.include_router(router)
