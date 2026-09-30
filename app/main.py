import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (so the tables are registered on Base)
from app.database import Base, engine
from app.routers import auth, bookings, centres, payments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="EVE Diagnostic Bookings API",
    description="Book diagnostic tests and pay for them (payments are simulated).",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(centres.router)
app.include_router(bookings.router)
app.include_router(payments.router)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
