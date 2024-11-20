import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from zoom_utils import validate_zoom_request, get_meeting_summary
from openai_utils import determine_slack_channel
from slack_utils import post_to_slack, join_slack_channel

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
ZOOM_WEBHOOK_SECRET_TOKEN = os.getenv('ZOOM_WEBHOOK_SECRET_TOKEN')

@app.route("/zoom-webhook", methods=["POST"])
def zoom_webhook():
    try:
        zoom_signature = request.headers.get('x-zm-signature')
        zoom_timestamp = request.headers.get('x-zm-request-timestamp')
        data = request.get_json()

        # Validate Zoom request
        if not validate_zoom_request(ZOOM_WEBHOOK_SECRET_TOKEN, zoom_signature, zoom_timestamp, data):
            return "Unauthorized request", 401

        # Handle URL validation event
        if data.get('event') == 'endpoint.url_validation':
            return jsonify({
                "plainToken": data['payload']['plainToken'],
                "encryptedToken": "Your encrypted token here"
            })

        # Handle Recording Completed event
        if data.get('event') == 'recording.completed':
            meeting_id = data['payload']['object']['id']
            meeting_topic = data['payload']['object']['topic']

            print(f"Fetching meeting summary for meeting ID: {meeting_id}")
            meeting_summary = get_meeting_summary(meeting_id)

            print(f"Determining Slack channel for meeting topic: '{meeting_topic}' and summary: '{meeting_summary}'")
            slack_channel = determine_slack_channel(meeting_topic, meeting_summary)

            if slack_channel:
                channel_id = join_slack_channel(slack_channel.lstrip('#'))
                post_to_slack(channel_id, f"Meeting Summary for '{meeting_topic}':\n{meeting_summary}")

            return "Event received", 200

        return "No action taken", 200

    except Exception as e:
        print(f"Error processing webhook: {e}")
        return "Internal Server Error", 500

if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv('PORT', 5000)))
