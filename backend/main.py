import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import Base, engine
from backend.routers import disputes, health

app = FastAPI(title="Invoice Dispute Investigation API")

frontend_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in frontend_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(disputes.router)


@app.on_event("startup")
def on_startup():
    """Create all tables if they don't already exist (SQLite dev DB by
    default; set DATABASE_URL for Postgres/etc in other environments)."""
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"message": "Backend API is running"}
