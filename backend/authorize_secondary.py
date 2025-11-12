import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_SECRET_FILE = 'credentials_secondary.json'

# 🔹 Usar los scopes actualizados que Google recomienda
SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly"
]

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
creds = flow.run_local_server(port=0)

with open('token_secondary.pkl', 'wb') as token_file:
    pickle.dump(creds, token_file)

print("✅ Token guardado correctamente en token_secondary.pkl")