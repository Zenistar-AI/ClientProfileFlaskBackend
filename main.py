from flask import Flask, request, jsonify
from supabase import create_client, Client
from datetime import datetime
import openai
import os
import json
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Initialize Flask app and Supabase client
app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route("/")
def health_check():
    return "Gmail Add-on backend is live!"

def get_email_thread(profile_id, latest_email):
    messages_response = supabase.table("messages") \
        .select("content") \
        .eq("profile_id", profile_id) \
        .order("timestamp", desc=False) \
        .execute()
    history = [msg["content"] for msg in messages_response.data]
    return "\n\n".join(history + [latest_email])

def is_client_email(full_thread):
    prompt = f"""Determine if the following email thread is a conversation with a client.
Only respond with "Yes" or "No".

Thread:
{full_thread}
"""
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    decision = response.choices[0].message.content.strip().lower()
    print("OpenAI client check response:", decision)
    return "yes" in decision

def extract_client_profile(full_thread):
    prompt = f"""Analyze the following email thread and extract the client's:
- Preferences
- Timeline
- Concerns

Return a JSON object exactly like this:
{{
  "preferences": "...",
  "timeline": "...",
  "concerns": "..."
}}

Do not include any explanation.

Thread:
{full_thread}
"""
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.choices[0].message.content)

@app.route("/get-or-create-profile", methods=["POST"])
def get_or_create_profile():
    try:
        data = request.get_json()
        email = data.get("email")
        latest_email = data.get("latestEmailContent", "").strip()

        if not email:
            return jsonify({"error": "Missing email"}), 400

        # Step 1: Look up profile
        result = supabase.table("profiles").select("*").eq("email", email).execute()
        profile = result.data[0] if result.data else None
        is_new_profile = False

        # Step 2: Create if not found
        if not profile:
            insert_result = supabase.table("profiles").insert({
                "email": email,
                "name": "Unknown",
                "preferences": "",
                "timeline": "",
                "concerns": "",
                "notes": "",
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
            profile = insert_result.data[0]
            is_new_profile = True

        profile_id = profile["id"]

        # Step 3: Check for duplicate message
        existing_messages = supabase.table("messages") \
            .select("id") \
            .eq("profile_id", profile_id) \
            .eq("content", latest_email) \
            .execute()

        if not existing_messages.data:
            # Step 4: Add message to history
            supabase.table("messages").insert({
                "profile_id": profile_id,
                "content": latest_email,
                "timestamp": datetime.utcnow().isoformat()
            }).execute()

            # Step 5: Get full thread and use OpenAI
            full_thread = get_email_thread(profile_id, latest_email)
            print("Full email thread:\n", full_thread)

            if is_client_email(full_thread):
                try:
                    structured = extract_client_profile(full_thread)
                    print("Extracted profile from OpenAI:", structured)

                    update_result = supabase.table("profiles").update({
                        "preferences": structured.get("preferences", ""),
                        "timeline": structured.get("timeline", ""),
                        "concerns": structured.get("concerns", ""),
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("id", profile_id).execute()

                    print("Supabase update result:", update_result)
                except Exception as e:
                    print("Failed to parse or update profile:", e)
            else:
                print("Message identified as NOT from a client.")
                supabase.table("profiles").update({
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("id", profile_id).execute()

        # Step 6: Return profile
        updated_result = supabase.table("profiles").select("*").eq("id", profile_id).execute()
        updated_profile = updated_result.data[0]

        return jsonify({
            "name": updated_profile.get("name", "Unknown"),
            "preferences": updated_profile.get("preferences", ""),
            "timeline": updated_profile.get("timeline", ""),
            "concerns": updated_profile.get("concerns", ""),
            "notes": updated_profile.get("notes", "")
        })

    except Exception as e:
        print("Top-level error in /get-or-create-profile:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/update-notes", methods=["POST"])
def update_notes():
    try:
        data = request.get_json()
        email = data.get("email")
        notes = data.get("notes", "").strip()

        if not email:
            return jsonify({"error": "Missing email"}), 400

        result = supabase.table("profiles").select("id").eq("email", email).execute()
        if not result.data:
            return jsonify({"error": "Profile not found"}), 404

        profile_id = result.data[0]["id"]

        supabase.table("profiles").update({
            "notes": notes,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", profile_id).execute()

        return jsonify({"status": "success"})

    except Exception as e:
        print("Error in /update-notes:", e)
        return jsonify({"error": str(e)}), 500
