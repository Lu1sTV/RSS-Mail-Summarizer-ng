import csv
from datetime import datetime
from collections import defaultdict
import firebase_admin
from firebase_admin import credentials, firestore

# ---- Firestore Setup ----
# Load service account key (must be in same folder)
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

# Initialize Firestore client
db = firestore.client()

def count_entries_by_time_of_day():
    # Dictionary to store counts per date
    date_counts = defaultdict(lambda: {"morning": 0, "evening": 0})

    # Fetch all documents from 'website' collection
    docs = db.collection("website").stream()

    for doc in docs:
        data = doc.to_dict()
        timestamp_str = data.get("timestamp")
        if not timestamp_str:
            continue  # Skip if no timestamp

        try:
            # Parse timestamp string to datetime object
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
            date_str = dt.date().isoformat()
            hour = dt.hour

            # Classify time of day
            if 6 <= hour < 12:
                date_counts[date_str]["morning"] += 1
            elif 15 <= hour < 21:
                date_counts[date_str]["evening"] += 1

        except ValueError:
            print(f"⚠️  Skipping unparseable timestamp: {timestamp_str}")

    return date_counts

def save_counts_to_csv(date_counts, filename="entry_counts.csv"):
    with open(filename, mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["date", "morning_count", "evening_count"])
        for date in sorted(date_counts.keys()):
            counts = date_counts[date]
            writer.writerow([date, counts["morning"], counts["evening"]])
    print(f"✅ Saved results to {filename}")

if __name__ == "__main__":
    print("🔄 Reading Firestore entries...")
    counts = count_entries_by_time_of_day()
    save_counts_to_csv(counts)
