from flask import Flask, request, jsonify
from supabase import create_client, Client
from datetime import datetime
import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route("/")
def health_check():
    return "Gmail Add-on backend is live!"

@app.route("/get-or-create-profile", methods=["POST"])
def get_or_create_profile():
    try:
        data = request.get_json()
        email = data.get("email")
        latest_email = data.get("latestEmailContent", "").strip()

        if not email:
            return jsonify({"error": "Missing email"}), 400

        # 1. Look up profile
        result = supabase.table("profiles").select("*").eq("email", email).execute()
        profile = result.data[0] if result.data else None

        if not profile:
            # 2. Create new profile
            insert_result = supabase.table("profiles").insert({
                "email": email,
                "name": "Unknown",
                "preferences": "To be updated",
                "timeline": "To be updated",
                "concerns": "N/A",
                "notes": latest_email,
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
            profile = insert_result.data[0]

        # 3. Get profile ID
        profile_id = profile["id"]

        # 4. Check if this message already exists
        existing_messages = supabase.table("messages") \
            .select("id") \
            .eq("profile_id", profile_id) \
            .eq("content", latest_email) \
            .execute()

        if not existing_messages.data:
            # 5. Insert message into history
            supabase.table("messages").insert({
                "profile_id": profile_id,
                "content": latest_email,
                "timestamp": datetime.utcnow().isoformat()
            }).execute()

            # 6. Optionally update notes/timeline/preferences here

            supabase.table("profiles").update({
                "notes": (profile.get("notes", "") + "\n\n" + latest_email).strip(),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", profile_id).execute()

        # 7. Return display profile
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
        return jsonify({"error": str(e)}), 500
