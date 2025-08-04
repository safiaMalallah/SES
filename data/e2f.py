import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate("firebase_key.json")  # Ensure this file exists
firebase_admin.initialize_app(cred)
db = firestore.client()

# Load Excel
df = pd.read_excel("corrected_question_bank.xlsx")

# Upload to Firestore
collection = db.collection("question_bank")

for index, row in df.iterrows():
    doc_data = {
        "id": row["id"],
        "question_en": row["question_en"],
        "question_ar": row["question_ar"],
        "category": row["category"],
        "correct_id": str(row["correct_id"]),
        "answers": {
            "A_en": row["A_en"],
            "A_ar": row["A_ar"],
            "B_en": row["B_en"],
            "B_ar": row["B_ar"],
            "C_en": row["C_en"],
            "C_ar": row["C_ar"],
            "D_en": row["D_en"],
            "D_ar": row["D_ar"]
        }
    }

    # Firestore doc ID will be auto-generated
    collection.add(doc_data)

print("✅ Upload completed successfully.")
