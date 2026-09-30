"""Adds an admin user and some sample centres/tests.
Run with: python -m app.seed
"""
from decimal import Decimal

from app.config import ADMIN_EMAIL, ADMIN_PASSWORD
from app.database import Base, SessionLocal, engine
from app.models import Centre, CentreTest, DiagnosticTest, User
from app.security import hash_password

TESTS = [
    ("Complete Blood Count (CBC)", "Checks red cells, white cells and platelets"),
    ("Lipid Profile", "Cholesterol and triglycerides"),
    ("Thyroid Profile (T3, T4, TSH)", "Thyroid function test"),
    ("HbA1c", "Average blood sugar over the last 3 months"),
    ("Vitamin D", "25-hydroxy vitamin D level"),
]

# centre name, location, {test name: price}
CENTRES = [
    ("EVE Diagnostics Saket", "New Delhi", {
        "Complete Blood Count (CBC)": "350",
        "Lipid Profile": "600",
        "Thyroid Profile (T3, T4, TSH)": "550",
        "Vitamin D": "1200",
    }),
    ("EVE Diagnostics Sector 18", "Noida", {
        "Complete Blood Count (CBC)": "300",
        "HbA1c": "450",
        "Vitamin D": "1100",
    }),
    ("EVE Diagnostics DLF Phase 3", "Gurugram", {
        "Lipid Profile": "650",
        "Thyroid Profile (T3, T4, TSH)": "500",
        "HbA1c": "500",
    }),
]


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(email=ADMIN_EMAIL).first():
            db.add(User(name="Admin", email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD), is_admin=True))
            print(f"Created admin user {ADMIN_EMAIL}")

        tests = {}
        for name, description in TESTS:
            test = db.query(DiagnosticTest).filter_by(name=name).first()
            if not test:
                test = DiagnosticTest(name=name, description=description)
                db.add(test)
            tests[name] = test
        db.flush()

        for centre_name, location, prices in CENTRES:
            if db.query(Centre).filter_by(name=centre_name).first():
                continue
            centre = Centre(name=centre_name, location=location)
            db.add(centre)
            db.flush()
            for test_name, price in prices.items():
                db.add(CentreTest(centre_id=centre.id, test_id=tests[test_name].id, price=Decimal(price)))
            print(f"Created centre {centre_name}")

        db.commit()
        print("Seeding done")
    finally:
        db.close()


if __name__ == "__main__":
    run()
