import sys
sys.path.insert(0, r"C:\Users\chait\Desktop\FINAL")
from backend.database import SessionLocal
from sqlalchemy import text

def run_migration():
    db = SessionLocal()
    try:
        print("Applying migration: updating train_schedule_status_check constraint...")
        db.execute(text("ALTER TABLE train_schedule DROP CONSTRAINT IF EXISTS train_schedule_status_check;"))
        db.execute(text("ALTER TABLE train_schedule ADD CONSTRAINT train_schedule_status_check CHECK (status IN ('scheduled', 'running', 'completed', 'cancelled', 'diverted'));"))
        db.commit()
        print("Migration applied successfully!")
        
        # Verify
        res = db.execute(text("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'train_schedule_status_check';")).fetchall()
        print("Updated constraint:", res)
    except Exception as e:
        db.rollback()
        print(f"Migration error: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
