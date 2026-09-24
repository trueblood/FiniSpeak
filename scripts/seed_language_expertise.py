import firebase_admin
from firebase_admin import credentials, firestore

# Uses Application Default Credentials
FIREBASE_PROJECT_ID = "finispeak"

if not firebase_admin._apps:
    firebase_admin.initialize_app(
        options={
            "projectId": FIREBASE_PROJECT_ID
        }
    )

db = firestore.client()


LANGUAGES = [
    "English",
    "Spanish",
    "French",
    "German",
    "Italian",
    "Portuguese",
    "Mandarin Chinese",
    "Cantonese",
    "Japanese",
    "Korean",
    "Arabic",
    "Hindi",
    "Urdu",
    "Bengali",
    "Punjabi",
    "Vietnamese",
    "Tagalog",
    "Russian",
    "Ukrainian",
    "Polish",
    "Dutch",
    "Greek",
    "Turkish",
    "Hebrew",
    "Persian / Farsi",
    "Swahili",
    "Somali",
    "Haitian Creole",
    "American Sign Language (ASL)",
]


DIALECTS = [
    "American English",
    "British English",
    "Canadian English",
    "Australian English",

    "Mexican Spanish",
    "Caribbean Spanish",
    "Puerto Rican Spanish",
    "Cuban Spanish",
    "Dominican Spanish",
    "Central American Spanish",
    "South American Spanish",
    "Castilian Spanish",

    "Brazilian Portuguese",
    "European Portuguese",

    "Canadian French",
    "European French",

    "Mandarin Chinese",
    "Cantonese",

    "Modern Standard Arabic",
    "Egyptian Arabic",
    "Levantine Arabic",
    "Gulf Arabic",
    "Maghrebi Arabic",

    "European Russian",

    "Indian English",
    "Pakistani English",

    "Latin American",
    "Caribbean",
    "Central American",
    "South American",
    "North American",
    "European",
    "Middle Eastern",
    "North African",
    "West African",
    "East African",
    "South Asian",
    "Southeast Asian",
]


SPECIALTIES = [
    "Medical",
    "Healthcare",
    "Mental Health",
    "Emergency Medicine",
    "Pharmacy",
    "Dental",

    "Legal",
    "Court",
    "Immigration",
    "Law Enforcement",

    "Education",
    "K-12 Education",
    "Higher Education",
    "Special Education",

    "Social Services",
    "Community Services",
    "Nonprofit",

    "Business",
    "Finance",
    "Banking",
    "Insurance",
    "Real Estate",

    "Technology",
    "Software / IT",
    "Engineering",

    "Government",
    "Public Services",

    "Customer Service",
    "Retail",
    "Hospitality",
    "Travel / Tourism",

    "Human Resources",
    "Employment",

    "Housing",
    "Transportation",

    "General Interpretation",
]


def slug(value):
    return (
        value.lower()
        .replace("/", " ")
        .replace("(", "")
        .replace(")", "")
        .replace("-", " ")
        .replace("  ", " ")
        .strip()
        .replace(" ", "-")
    )


def seed_collection(collection_name, values):
    print(f"\nSeeding {collection_name}...")

    batch = db.batch()

    for value in values:
        document_id = slug(value)

        ref = db.collection(collection_name).document(document_id)

        batch.set(
            ref,
            {
                "name": value,
                "nameLower": value.lower(),
                "active": True,
                "seeded": True,
            },
            merge=True,
        )

    batch.commit()

    print(f"Added/updated {len(values)} records.")


def main():
    seed_collection("reference_languages", LANGUAGES)
    seed_collection("reference_dialects", DIALECTS)
    seed_collection("reference_specialties", SPECIALTIES)

    print("\nFiniSpeak language expertise seed complete.")


if __name__ == "__main__":
    main()
