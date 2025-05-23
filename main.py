from flask import Flask, request, jsonify
from supabase import create_client, Client
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app and Supabase
app = Flask(__name__)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route("/")
def health_check():
    return "✅ Gmail Add-on backend is live!"

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
                "preferences": "To be updated",
                "timeline": "To be updated",
                "concerns": "N/A",
                "notes": "",  # Start with empty notes
                "updated_at": datetime.utcnow().isoformat()
            }).execute()
            profile = insert_result.data[0]
            is_new_profile = True

        profile_id = profile["id"]

        # Step 3: Check for duplicate messages
        existing_messages = supabase.table("messages") \
            .select("id") \
            .eq("profile_id", profile_id) \
            .eq("content", latest_email) \
            .execute()

        if not is_new_profile and not existing_messages.data:
            # Step 4: Add message (without modifying notes)
            supabase.table("messages").insert({
                "profile_id": profile_id,
                "content": latest_email,
                "timestamp": datetime.utcnow().isoformat()
            }).execute()

            # Step 5: Update timestamp only
            supabase.table("profiles").update({
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", profile_id).execute()

        # Step 6: Return full profile
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

@app.route("/update-notes", methods=["POST"])
def update_notes():
    try:
        data = request.get_json()
        email = data.get("email")
        notes = data.get("notes", "").strip()

        if not email:
            return jsonify({"error": "Missing email"}), 400

        # Lookup profile
        result = supabase.table("profiles").select("id").eq("email", email).execute()
        if not result.data:
            return jsonify({"error": "Profile not found"}), 404

        profile_id = result.data[0]["id"]

        # Update notes field
        supabase.table("profiles").update({
            "notes": notes,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", profile_id).execute()

        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
