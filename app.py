import os
import json
import requests
import hmac
import hashlib
import base64
import time
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import openai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Load tokens and keys from environment variables
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
ZOOM_WEBHOOK_SECRET_TOKEN = os.getenv('ZOOM_WEBHOOK_SECRET_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ZOOM_CLIENT_ID = os.getenv('ZOOM_CLIENT_ID')
ZOOM_CLIENT_SECRET = os.getenv('ZOOM_CLIENT_SECRET')
ZOOM_ACCOUNT_ID = os.getenv('ZOOM_ACCOUNT_ID')

slack_client = WebClient(token=SLACK_BOT_TOKEN)
openai.api_key = OPENAI_API_KEY

@app.route('/zoom-webhook', methods=['POST'])
def zoom_webhook():
    try:
        # Parse incoming JSON request
        data = request.json

        # Extract headers for verification
        zoom_signature = request.headers.get('x-zm-signature')
        zoom_timestamp = request.headers.get('x-zm-request-timestamp')

        # Check if the timestamp is within 5 minutes of current time to prevent replay attacks
        if abs(time.time() - int(zoom_timestamp)) > 300:
            print("Unauthorized request: Timestamp is too old.")
            return jsonify({'message': 'Unauthorized'}), 401

        # Validate the request is from Zoom
        message = f'v0:{zoom_timestamp}:{json.dumps(data, separators=(
