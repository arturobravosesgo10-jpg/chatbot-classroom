import pickle
from googleapiclient.discovery import build

with open('token_secondary.pkl', 'rb') as token_file:
    creds = pickle.load(token_file)

service = build('classroom', 'v1', credentials=creds)
courses = service.courses().list().execute().get('courses', [])

if not courses:
    print("⚠️ No se encontraron clases para esta cuenta.")
else:
    print("✅ Clases disponibles:")
    for c in courses:
        print(f"{c['name']} → {c['id']}")
