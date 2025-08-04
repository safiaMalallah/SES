import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

print("📘 Reading Excel file...")
df = pd.read_excel("data/toefl_question.xlsx")
df.columns = df.columns.str.strip()

# ✅ Expected columns
expected = [
    "id", "category", "question_en", "question_ar", "correct_id",
    "A_en", "A_ar", "B_en", "B_ar", "C_en", "C_ar", "D_en", "D_ar"
]

missing = [col for col in expected if col not in df.columns]
if missing:
    print("❌ Missing required columns:", missing)
    exit(1)

# ✅ Firebase setup
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# 🗑️ Delete old documents
print("🗑️ Deleting existing questions in Firestore...")
for doc in db.collection("question_bank").stream():
    doc.reference.delete()
print("✅ Old questions deleted.")

# 🚀 Upload new questions
print("🚀 Uploading questions...")
for _, row in df.iterrows():
    question_id = str(row["id"])
    doc = {
        "id": question_id,
        "category": str(row["category"]),
        "question_en": str(row["question_en"]),
        "question_ar": str(row["question_ar"]),
        "correct_id": str(row["correct_id"]),
        "answers": {
            "A_en": str(row["A_en"]), "A_ar": str(row["A_ar"]),
            "B_en": str(row["B_en"]), "B_ar": str(row["B_ar"]),
            "C_en": str(row["C_en"]), "C_ar": str(row["C_ar"]),
            "D_en": str(row["D_en"]), "D_ar": str(row["D_ar"]),
        }
    }
    # ✅ Use question_id as document ID
    db.collection("question_bank").document(question_id).set(doc)
    print(f"✅ Uploaded: {question_id}")

print("🎉 All questions successfully uploaded.")
