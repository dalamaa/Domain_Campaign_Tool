from app import create_app
from app.models.models import db, EmailAccount


CODES = [
    'D03', 'D04', 'D05', 'D07',
    'M01', 'M02', 'M04', 'M05', 'M06', 'M07', 'M08', 'M09',
    'M10', 'M11', 'M12', 'M13', 'M14', 'M15', 'M16', 'M17',
    'M18', 'M19', 'M20',
    'ML06', 'ML07', 'ML08',
    'N04', 'N09', 'N10',
    'T01', 'T03', 'T04', 'T05', 'T06', 'T07', 'T08', 'T09',
    'T10', 'T12', 'T13', 'T14', 'T15', 'T16', 'T17', 'T18',
    'Y01', 'Y02', 'Y03', 'Y04',
    'Z00', 'Z01', 'Z04', 'Z08', 'Z09'
]


def restore_email_accounts():
    app = create_app()

    with app.app_context():
        inserted = 0
        skipped = 0

        for i, code in enumerate(CODES, start=1):
            existing = db.session.get(EmailAccount, code)

            if existing:
                skipped += 1
                continue

            group = 'ML' if code.startswith('ML') else code[0]

            account = EmailAccount(
                code=code,
                group=group,
                profile_order=i,
                enabled=True
            )

            db.session.add(account)
            inserted += 1

        db.session.commit()

        total = db.session.query(EmailAccount).count()

        print(f"Inserted: {inserted}")
        print(f"Skipped: {skipped}")
        print(f"Final EmailAccount count: {total}")


if __name__ == "__main__":
    restore_email_accounts()