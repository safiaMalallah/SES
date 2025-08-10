# upload_users.py
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import generate_password_hash

EXCEL_PATH = "data/users.xlsx"   # change if needed
FIREBASE_KEY = "firebase_key.json"

# Init Firebase
cred = credentials.Certificate(FIREBASE_KEY)
firebase_admin.initialize_app(cred)
db = firestore.client()

# Load Excel
df = pd.read_excel(EXCEL_PATH)
# normalize column names (strip & lowercase)
df.columns = [c.strip().lower() for c in df.columns]

required = {"email", "password", "role"}
missing = required - set(df.columns)
if missing:
    raise SystemExit(f"Missing columns in Excel: {missing}. Expected: {required}")

# Trim values
df["email"] = df["email"].astype(str).str.strip().str.lower()
df["password"] = df["password"].astype(str).str.strip()
df["role"] = df["role"].astype(str).str.strip().str.lower()

batch = db.batch()
users_col = db.collection("users")

count = 0
for _, row in df.iterrows():
    email = row["email"]
    if not email:
        continue
    pwd_hash = generate_password_hash(row["password"])
    role = row["role"] if row["role"] in ("admin", "student") else "student"

    # Use email as the document ID (simplifies lookups)
    doc_ref = users_col.document(email)
    batch.set(doc_ref, {
        "email": email,
        "password_hash": pwd_hash,
        "role": role,
        "active": True,
    })
    count += 1
    # Commit every 400 writes (batch limit)
    if count % 400 == 0:
        batch.commit()
        batch = db.batch()

# final commit
batch.commit()
print(f"✅ Uploaded/updated {count} users into Firestore 'users' collection.")
