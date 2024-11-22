# app.py

import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from zoom_utils import (
    validate_zoom_webhook,
    download_recording,
    get_meeting_participants,
    get_zoom_headers  # This may not be needed anymore
)
from slack_utils import get_channel_id, ensure_default_channel_exists, post_to_slack
from openai_utils import (
    transcribe_audio,
    generate_summary,
    determine_slack_channel
)
import requests
import openai
import tempfile
import json

# Define the default Slack channel name
DEFAULT_CHANNEL_NAME = "bot-lost-meeting-recordings"

# Load environment variables from .env file only if not on Heroku
if os.getenv('DYNO') is None:
    load_dotenv()

# Configure logging to stdout
import sys

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

ZOOM_WEBHOOK_SECRET_TOKEN = os.getenv('ZOOM_WEBHOOK_SECRET_TOKEN')

if not ZOOM_WEBHOOK_SECRET_TOKEN:
    logger.error("ZOOM_WEBHOOK_SECRET_TOKEN is not set in environment variables.")
    raise EnvironmentError("ZOOM_WEBHOOK_SECRET_TOKEN is required.")

@app.route('/zoom-webhook', methods=['POST'])
def zoom_webhook():
    try:
        data = request.get_json()
        if not data:
            logger.warning("Invalid request: No data provided.")
            return jsonify({'message': 'Invalid request: No data provided'}), 400

        zoom_signature = request.headers.get('x-zm-signature')
        zoom_timestamp = request.headers.get('x-zm-request-timestamp')

        if not zoom_signature or not zoom_timestamp:
            logger.warning("Invalid request: Missing signature or timestamp headers.")
            return jsonify({'message': 'Invalid request: Missing signature or timestamp headers.'}), 400

        # Reconstruct the payload as a JSON string without spaces
        payload = json.dumps(data, separators=(',', ':'))
        print(payload)

        # Validate request from Zoom
        if not validate_zoom_webhook(ZOOM_WEBHOOK_SECRET_TOKEN, zoom_signature, zoom_timestamp, payload):
            logger.warning("Unauthorized request: Validation failed.")
            return jsonify({'message': 'Unauthorized'}), 401

        event = data.get('event')
        if event == 'recording.completed':

            recording_info = data['payload']['object']
            meeting_topic = recording_info.get('topic', 'No topic')
            meeting_id = str(recording_info.get('id'))  # Ensure it's string
            meeting_uuid = recording_info.get('uuid')  # UUID
            host_email = recording_info.get('host_email', 'No host email provided')

            if not meeting_id or not meeting_uuid:
                logger.warning("Invalid request: Missing meeting ID or UUID.")
                return jsonify({'message': 'Invalid request: Missing meeting ID or UUID'}), 400

            logger.info(f"Processing recording.completed event for Meeting ID: {meeting_id}")

            # Extract download_url and download_token directly from the webhook payload
            # Depending on Zoom's webhook payload structure, adjust the keys accordingly
            # Here's an example based on typical Zoom webhook payloads
            recording_files = recording_info.get('recording_files', [])
            if not recording_files:
                logger.warning(f"No recordings found in webhook payload for Meeting ID: {meeting_id}")
                return jsonify({'message': 'No recordings available in payload.'}), 200

            # Iterate through recording files to find the desired one (e.g., video)
            recording_url = None
            download_token = None
            for file in recording_files:
                if file.get('file_type') == 'MP4':  # Adjust as needed
                    recording_url = file.get('download_url')
                    download_token = file.get('download_token')
                    break

            if not recording_url or not download_token:
                logger.error("Recording URL or download token not found in webhook payload.")
                return jsonify({'message': 'Recording URL or download token is missing.'}), 400

            # Additional Meeting Details
            start_time = recording_info.get('start_time', 'Unknown DateTime')
            if 'T' in start_time and 'Z' in start_time:
                meeting_date = start_time.split('T')[0]
                meeting_time = start_time.split('T')[1].split('Z')[0]
            else:
                meeting_date = "Unknown Date"
                meeting_time = "Unknown Time"

            # Handle participants extraction
            participants_data = get_meeting_participants(meeting_id)
            if participants_data:
                participants = [participant['user_email'] for participant in participants_data if participant.get('user_email')]
                if not participants:
                    participants = ["Unknown Participant"]
            else:
                participants = ["Unknown Participant"]

            duration = recording_info.get('duration', 'Unknown Duration')

            # Download the recording using download_token
            recording_file_path = download_recording(recording_url, download_token)
            if not recording_file_path:
                logger.error("Failed to download recording.")
                return jsonify({'message': 'Failed to download recording.'}), 400

            # Transcribe the recording
            transcript = transcribe_audio(recording_file_path)
            if not transcript:
                logger.warning("Transcription failed.")
                transcript = "No transcription available."

            # Generate summary using OpenAI
            meeting_summary = generate_summary(
                transcript=transcript,
                meeting_title=meeting_topic,
                host_email=host_email,
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                meeting_time=meeting_time,
                participants=participants,
                duration=duration
            )
            if not meeting_summary:
                logger.warning("Summary generation failed.")
                meeting_summary = {
                    "meeting_details": {
                        "title": meeting_topic,
                        "date_time": f"{meeting_date} at {meeting_time}",
                        "host_email": host_email,
                        "meeting_id": meeting_id,
                        "participants": participants,
                        "duration": duration
                    },
                    "share_details": {
                        "play_url": "No play URL available.",
                        "password": "No password available."
                    },
                    "meeting_summary": {
                        "summary_overview": "No overview available.",
                        "main_topics": [],
                        "action_items": []
                    }
                }

            # Incorporate Share Details (Play URL and Password)
            share_details = {
                "play_url": recording_url,
                "password": recording_info.get('play_passcode', 'No password available.')
            }

            # Update share_details in meeting_summary
            meeting_summary['share_details'] = share_details

            # Determine Slack channel using OpenAI
            slack_channel = determine_slack_channel(meeting_topic, meeting_summary.get('meeting_summary', {}))
            logger.info(f"Determined Slack channel: {slack_channel}")

            # Get channel ID
            channel_id = get_channel_id(slack_channel)
            if not channel_id:
                logger.warning(f"Slack channel '{slack_channel}' not found. Attempting to post to default channel '{DEFAULT_CHANNEL_NAME}'.")
                # Ensure default channel exists
                channel_id = ensure_default_channel_exists(DEFAULT_CHANNEL_NAME)
                if not channel_id:
                    logger.error("Failed to find or create the default Slack channel. Cannot post the meeting summary.")
                    return jsonify({'message': 'Failed to post the meeting summary to Slack.'}), 500

            # Prepare the summary message
            summary = meeting_summary.get('meeting_summary', {})
            recording_summary = (
                f"*Meeting Title & Basic Details:*\n"
                f"- **Title:** {meeting_summary['meeting_details']['title']}\n"
                f"- **Date & Time:** {meeting_summary['meeting_details']['date_time']}\n"
                f"- **Host Email:** {meeting_summary['meeting_details']['host_email']}\n"
                f"- **Meeting ID:** {meeting_summary['meeting_details']['meeting_id']}\n\n"
                f"*Share Details:*\n"
                f"- **Play URL:** {meeting_summary['share_details']['play_url']}\n"
                f"- **Password:** {meeting_summary['share_details']['password']}\n\n"
                f"*Meeting Summary:*\n"
                f"- **Brief Overview:** {summary.get('summary_overview', 'No overview available.')}\n"
                f"- **Main Topics Discussed:**\n"
            )

            # Add main topics
            for topic in summary.get('main_topics', []):
                recording_summary += f"  - **{topic['topic']}** (Timestamp: {topic['timestamp']})\n"

            # Add action items
            recording_summary += "\n- **Action Items:**\n"
            for action in summary.get('action_items', []):
                recording_summary += f"  - **{action['action_item']}** (Responsible: {action['responsible']})\n"

            # Post to Slack
            success = post_to_slack(channel_id, recording_summary)
            if success:
                logger.info(f"Posted meeting summary to Slack channel ID '{channel_id}'.")
            else:
                logger.error(f"Failed to post meeting summary to Slack channel ID '{channel_id}'.")

            # Clean up the downloaded recording file
            try:
                os.remove(recording_file_path)
                logger.info(f"Removed temporary recording file: {recording_file_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file: {recording_file_path}. Error: {e}")

    except Exception as e:
        logger.exception(f"Error processing Zoom webhook: {e}")
        return jsonify({'message': 'Internal server error.'}), 500

    return jsonify({'message': 'Event received'}), 200

@app.route('/', methods=['GET'])
def index():
    return "The Zoom to Slack integration app is running successfully!", 200

if __name__ == '__main__':
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
    except Exception as e:
        logger.exception(f"Failed to start the Flask app: {e}")
