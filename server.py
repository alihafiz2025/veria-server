from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import uuid
import json
from dotenv import load_dotenv
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Load environment variables
load_dotenv()

# Flask app setup
app = Flask(__name__)
CORS(app)  # Enable CORSss

# Directory setup
INBOX_DIR = 'inbox'
META_DIR = 'inbox_metadata'
os.makedirs(INBOX_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)

# Load Google OAuth client ID
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
print(f"Loaded GOOGLE_CLIENT_ID: {GOOGLE_CLIENT_ID}")  # Debugging

# Routes
@app.route('/verify_token', methods=['POST'])
def verify_token():
    try:
        data = request.get_json()
        token = data.get('token') or data.get('id_token')

        if not token:
            return jsonify({'error': 'Missing token'}), 400

        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        return jsonify({
            'message': 'Token is valid',
            'user_id': idinfo['sub'],
            'email': idinfo['email']
        }), 200

    except ValueError:
        return jsonify({'error': 'Invalid token'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        token = request.form.get('id_token') or request.headers.get('Authorization')
        if not token:
            print("[Server] Missing ID token in form")  # Debug log
            return jsonify({'error': 'Missing ID token'}), 400

        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        sender_email_verified = idinfo['email']

        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400

        file = request.files['image']
        sender_email = request.form.get('sender_email')
        receiver_email = request.form.get('receiver_email')

        if not sender_email or not receiver_email:
            return jsonify({'error': 'Sender and receiver email required'}), 400

        if sender_email_verified != sender_email:
            return jsonify({'error': 'Sender email does not match verified token email'}), 403

        filename = f"{uuid.uuid4().hex}_{file.filename}"
        filepath = os.path.join(INBOX_DIR, filename)
        file.save(filepath)

        metadata = {
            'filename': filename,
            'sender_email': sender_email,
            'receiver_email': receiver_email
        }
        metadata_path = os.path.join(META_DIR, f"{filename}.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f)

        return jsonify({'message': 'Upload successful', 'filename': filename}), 200

    except ValueError:
        return jsonify({'error': 'Invalid token'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download_image():
    try:
        data = request.get_json()
        token = data.get('id_token')
        filename = data.get('filename')

        if not token or not filename:
            return jsonify({'error': 'Missing parameters'}), 400

        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        user_email = idinfo['email']

        path = os.path.join(INBOX_DIR, filename)
        if not os.path.exists(path):
            return jsonify({'error': 'Image not found'}), 404

        meta_path = os.path.join(META_DIR, f"{filename}.json")
        if not os.path.exists(meta_path):
            return jsonify({'error': 'Metadata not found'}), 404

        with open(meta_path, 'r') as f:
            meta = json.load(f)

        if meta.get('receiver_email') != user_email:
            return jsonify({'error': 'You are not authorized to download this image'}), 403

        return send_file(path, mimetype='image/png')

    except ValueError:
        return jsonify({'error': 'Invalid token'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/inbox/<receiver_email>', methods=['GET'])
def get_inbox(receiver_email):
    try:
        results = []
        for fname in os.listdir(META_DIR):
            if fname.endswith('.json'):
                meta_path = os.path.join(META_DIR, fname)
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                    if meta.get('receiver_email') == receiver_email:
                        results.append(meta)
        return jsonify(results), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
