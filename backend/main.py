from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import health, items

app = FastAPI(title="Backend API")

# Allow the local Vite dev server to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(items.router)


@app.get("/")
def root():
    return {"message": "Backend API is running"}
