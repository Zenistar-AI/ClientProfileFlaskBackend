
from flask import Flask, request, jsonify
from supabase import create_client, Client
from datetime import datetime
import openai
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai.api_key = OPENAI_API_KEY

def is_client_email(thread_text):
    prompt = f"You are a real estate agent. Determine if the following email thread is a conversation with a client or a potential client. Reply only with Yes or No.\n\n{thread_text}"
    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return "yes" in response.choices[0].message.content.strip().lower()

def extend_profile_with_message(profile, message):
    prompt = f"""Given the current client profile (which may be empty) and a new message (which may be the first message sent by the client), update the client's profile.
    If the client's name is mentioned in the email (e.g. "Hi, this is James"), use that as the name.
    
    Current Profile:
    {json.dumps(profile, indent=2)}

    New Email:
    \"\"\"{message}\"\"\"

    Return updated profile in this JSON format:
    {{
    "name": "...",
    "preferences": "...",
    "timeline": "...",
    "concerns": "..."
    }}
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
        full_thread = data.get("latestThreadContent", "").strip()
        if not email or not full_thread:
            return jsonify({"error": "Missing data"}), 400

        # Step 1: Check client status
        if not is_client_email(full_thread[:2000]):
            return jsonify({"message": "Not a client"}), 200

        # Step 2: Lookup or create profile
        result = supabase.table("profiles").select("*").eq("email", email).execute()
        profile = result.data[0] if result.data else None
        if not profile:
            profile = supabase.table("profiles").insert({
                "email": email,
                "name": "",
                "preferences": "",
                "timeline": "",
                "concerns": "",
                "notes": "",
                "updated_at": datetime.utcnow().isoformat()
            }).execute().data[0]
        profile_id = profile["id"]

        # Step 3: Get messages and find longest match
        messages = supabase.table("messages").select("id", "content").eq("profile_id", profile_id).execute().data
        replaced = False
        for msg in messages:
            if msg["content"] and msg["content"].strip() in full_thread:
                supabase.table("messages").delete().eq("id", msg["id"]).execute()
                supabase.table("messages").insert({
                    "profile_id": profile_id,
                    "content": full_thread,
                    "timestamp": datetime.utcnow().isoformat()
                }).execute()
                replaced = True
                break

        if not replaced:
            supabase.table("messages").insert({
                "profile_id": profile_id,
                "content": full_thread,
                "timestamp": datetime.utcnow().isoformat()
            }).execute()

        # Step 4: Extend profile from message
        latest_profile = {
            "preferences": profile.get("preferences", ""),
            "timeline": profile.get("timeline", ""),
            "concerns": profile.get("concerns", "")
        }

        updated = extend_profile_with_message(latest_profile, full_thread)

        supabase.table("profiles").update({
            "name": updated.get("name", profile.get("name", "")),
            "preferences": updated.get("preferences", ""),
            "timeline": updated.get("timeline", ""),
            "concerns": updated.get("concerns", ""),
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", profile_id).execute()


        final_profile = supabase.table("profiles").select("*").eq("id", profile_id).execute().data[0]
        return jsonify({
            "name": final_profile.get("name", ""),
            "preferences": final_profile.get("preferences", ""),
            "timeline": final_profile.get("timeline", ""),
            "concerns": final_profile.get("concerns", ""),
            "notes": final_profile.get("notes", "")
        })
    except Exception as e:
        print("Error in /get-or-create-profile:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/update-notes", methods=["POST"])
def update_notes():
    try:
        data = request.get_json()
        email = data.get("email")
        notes = data.get("notes", "").strip()
        if not email:
            return jsonify({"error": "Missing email"}), 400

        profile = supabase.table("profiles").select("id").eq("email", email).execute().data[0]
        supabase.table("profiles").update({
            "notes": notes,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", profile["id"]).execute()

        return jsonify({"status": "success"})
    except Exception as e:
        print("Error in /update-notes:", e)
        return jsonify({"error": str(e)}), 500
