import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/eve_bookings"
)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-please-change-in-production")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "60"))

# shared secret the (fake) payment provider sends in the X-Webhook-Secret header
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dev-webhook-secret")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@eve.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
