import json
import os

import firebase_admin
from firebase_admin import credentials, firestore


# Service Account Schlüssel laden
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

# Firestore-Client erstellen
db = firestore.client()


# def add_data():
#     users_ref = db.collection("users")
#     users_ref.add({"name": "Alice", "age": 25, "city": "Berlin"})
#
# add_data()

def get_users():
    users_ref = db.collection("users").stream()
    for user in users_ref:
        print(f"{user.id} => {user.to_dict()}")

get_users()

