import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from zoom_utils import validate_zoom_request, get_meeting_summary
from slack_utils import get_channel_id, join_slack_channel, post_to_slack
from openai_utils import determine_slack_channel

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

ZOOM_WEBHOOK_SECRET_TOKEN = os.getenv('ZOOM_WEBHOOK_SECRET_TOKEN')

@app.route('/zoom-webhook', methods=['POST'])
def zoom_webhook():
    try:
        import time
        data = request.json
        if not data:
            return jsonify({'message': 'Invalid request: No data provided'}), 400

        zoom_signature = request.headers.get('x-zm-signature')
        zoom_timestamp = request.headers.get('x-zm-request-timestamp')

        # Validate request from Zoom
        if not validate_zoom_request(ZOOM_WEBHOOK_SECRET_TOKEN, zoom_signature, zoom_timestamp, data):
            return jsonify({'message': 'Unauthorized'}), 401

        if data.get('event') == 'recording.completed':
            recording_info = data['payload']['object']
            meeting_topic = recording_info.get('topic', 'No topic')
            meeting_id = recording_info.get('id')
            host_email = recording_info.get('host_email', 'No host email provided')

            if not meeting_id:
                return jsonify({'message': 'Invalid request: Missing meeting ID'}), 400

            # Get meeting summary using Zoom API
            meeting_summary = get_meeting_summary(meeting_id)

            # Determine Slack channel using OpenAI
            slack_channel = determine_slack_channel(meeting_topic, meeting_summary)

            # Get channel ID and post to Slack
            channel_id = get_channel_id(slack_channel)
            if not channel_id:
                return jsonify({'message': 'Channel not found'}), 404

            join_slack_channel(channel_id)

            recording_summary = (
                f"Meeting Summary for {meeting_topic}\n"
                f"ID: {meeting_id}\n"
                f"Quick recap\n\n"
                f"{meeting_summary.get('summary_overview', 'No overview available.')}\n\n"
                f"Next steps\n\n"
                f"{', '.join(meeting_summary.get('next_steps', ['TBD']))}\n\n"
                f"Summary\n\n"
                f"{meeting_summary.get('summary_details', 'No detailed summary available.')}\n"
            )

            post_to_slack(channel_id, recording_summary)

        return jsonify({'message': 'Event received'}), 200

    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({'message': 'Internal Server Error'}), 500

@app.route('/', methods=['GET'])
def index():
    return "The Zoom to Slack integration app is running successfully!", 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
