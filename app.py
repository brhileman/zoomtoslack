import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from zoom_utils import validate_zoom_request, get_meeting_summary
from slack_utils import get_channel_id, join_slack_channel, post_to_slack
from openai_utils import determine_slack_channel

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
        data = request.json
        if not data:
            logger.warning("Invalid request: No data provided.")
            return jsonify({'message': 'Invalid request: No data provided'}), 400

        zoom_signature = request.headers.get('x-zm-signature')
        zoom_timestamp = request.headers.get('x-zm-request-timestamp')

        # Validate request from Zoom
        if not validate_zoom_request(ZOOM_WEBHOOK_SECRET_TOKEN, zoom_signature, zoom_timestamp, data):
            logger.warning("Unauthorized request: Validation failed.")
            return jsonify({'message': 'Unauthorized'}), 401

        event = data.get('event')
        if event == 'recording.completed':
            recording_info = data['payload']['object']
            meeting_topic = recording_info.get('topic', 'No topic')
            meeting_id = recording_info.get('id')
            host_email = recording_info.get('host_email', 'No host email provided')

            if not meeting_id:
                logger.warning("Invalid request: Missing meeting ID.")
                return jsonify({'message': 'Invalid request: Missing meeting ID'}), 400

            logger.info(f"Processing recording.completed event for Meeting ID: {meeting_id}")

            # Get meeting summary using Zoom API
            meeting_summary = get_meeting_summary(meeting_id)
            if not meeting_summary:
                logger.warning(f"No meeting summary found for Meeting ID: {meeting_id}")
                return jsonify({'message': 'No meeting summary available.'}), 200

            # Determine Slack channel using OpenAI
            slack_channel = determine_slack_channel(meeting_topic, meeting_summary)
            logger.info(f"Determined Slack channel: {slack_channel}")

            # Get channel ID and post to Slack
            channel_id = get_channel_id(slack_channel)
            if not channel_id:
                logger.error(f"Slack channel '{slack_channel}' not found.")
                return jsonify({'message': 'Channel not found'}), 404

            joined = join_slack_channel(slack_channel)
            if not joined:
                logger.error(f"Failed to join Slack channel '{slack_channel}'.")
                return jsonify({'message': 'Failed to join Slack channel'}), 500

            recording_summary = (
                f"*Meeting Summary for {meeting_topic}*\n"
                f"*ID:* {meeting_id}\n"
                f"*Host Email:* {host_email}\n\n"
                f"*Quick Recap:*\n{meeting_summary.get('summary_overview', 'No overview available.')}\n\n"
                f"*Next Steps:*\n- " + "\n- ".join(meeting_summary.get('next_steps', ['TBD'])) + "\n\n"
                f"*Detailed Summary:*\n{meeting_summary.get('summary_details', 'No detailed summary available.')}"
            )

            post_to_slack(channel_id, recording_summary)
            logger.info(f"Posted meeting summary to Slack channel '{slack_channel}'.")

        return jsonify({'message': 'Event received'}), 200

    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return jsonify({'message': 'Internal Server Error'}), 500

@app.route('/', methods=['GET'])
def index():
    return "The Zoom to Slack integration app is running successfully!", 200

if __name__ == '__main__':
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
    except Exception as e:
        logger.exception(f"Failed to start the Flask app: {e}")
