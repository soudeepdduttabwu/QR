import os
import cv2
import numpy as np
from flask import Flask, request, jsonify, render_template, Response
import mysql.connector
from flask_cors import CORS

app = Flask(__name__)

# Enable CORS to allow mobile access
CORS(app)

# Configure MySQL Database
db_config = {
    'host': 'localhost',  # Replace with your database hostname
    'user': 'root',       # Replace with your database username
    'password': '1234',   # Replace with your database password
    'database': 'qr'      # Replace with your database name
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Helper function to validate file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Match QR Code Data
def match_qr_data(data):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute("SELECT name FROM user WHERE qr_data = %s", (data,))
        result = cursor.fetchone()
        connection.close()
        return result[0] if result else None
    except mysql.connector.Error as e:
        print(f"Database Error: {e}")
        return None

# Read QR Code from Image
def read_qr_from_image(image):
    detector = cv2.QRCodeDetector()
    
    # Handle image input (can be file path or numpy array)
    if isinstance(image, str):
        img = cv2.imread(image)
    else:
        img = image

    if img is None:
        return "Error: Unable to load the image."

    data, bbox, _ = detector.detectAndDecode(img)
    if data:
        user = match_qr_data(data)
        if user:
            return f"User '{user}' is present!"
        else:
            return "No match found in the database."
    else:
        return "No QR Code detected in the image."

# Camera Streaming
class VideoCamera:
    def __init__(self):
        self.video = cv2.VideoCapture(0)  # Use default camera
        self.is_scanning = False
        self.last_scan_result = None

    def __del__(self):
        self.video.release()

    def get_frame(self):
        success, image = self.video.read()
        
        if not success:
            return None

        # Optional: Add QR Code scanning during streaming
        if self.is_scanning:
            detector = cv2.QRCodeDetector()
            data, bbox, _ = detector.detectAndDecode(image)
            
            if data:
                # Stop scanning after first successful detection
                self.is_scanning = False
                self.last_scan_result = match_qr_data(data)

                # Optionally, draw a rectangle around detected QR code
                if bbox is not None:
                    bbox = bbox.astype(int)
                    cv2.polylines(image, [bbox], True, (0, 255, 0), 3)

        # Convert image to JPEG for streaming
        ret, jpeg = cv2.imencode('.jpg', image)
        return jpeg.tobytes()

    def start_scanning(self):
        self.is_scanning = True
        self.last_scan_result = None

    def stop_scanning(self):
        self.is_scanning = False

# Global camera instance
camera = VideoCamera()

# Web App Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'qr_image' not in request.files:
        return jsonify({'message': 'No file uploaded'}), 400

    file = request.files['qr_image']
    if file.filename == '':
        return jsonify({'message': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'message': 'Invalid file format. Only PNG, JPG, and JPEG are allowed.'}), 400

    # Read file as numpy array
    file_bytes = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

    # Process the QR code
    result = read_qr_from_image(img)

    return jsonify({'result': result})

# Camera streaming routes
@app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            frame = camera.get_frame()
            if frame is None:
                break
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')
    return Response(generate(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/start_scan', methods=['POST'])
def start_scan():
    camera.start_scanning()
    return jsonify({'message': 'Scanning started'})

@app.route('/stop_scan', methods=['POST'])
def stop_scan():
    camera.stop_scanning()
    return jsonify({'message': 'Scanning stopped'})

@app.route('/scan_result', methods=['GET'])
def scan_result():
    if camera.last_scan_result:
        return jsonify({
            'found': True, 
            'result': camera.last_scan_result
        })
    return jsonify({'found': False})

if __name__ == "__main__":
    # Ensure uploads directory exists
    os.makedirs('uploads', exist_ok=True)
    
    # Run the Flask app
    app.run(debug=True, host="0.0.0.0") 