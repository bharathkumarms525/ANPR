from flask import Flask, render_template, Response, jsonify
from camera_processor import CameraProcessor
import threading
from pymongo import MongoClient
from datetime import datetime
import pytz
import os

app = Flask(__name__)

# MongoDB Configuration
MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client['vehicle_management']
vehicles_col = db['vehicles']
employees_col = db['employee_vehicles']

# Initialize camera processors
entry_camera = CameraProcessor(camera_id=0, camera_type="entry")
exit_camera = CameraProcessor(camera_id=1, camera_type="exit")

# Ensure snapshot directories exist
os.makedirs('snapshots/entry', exist_ok=True)
os.makedirs('snapshots/exit', exist_ok=True)

def get_ist_time():
    return datetime.now(pytz.timezone('Asia/Kolkata'))

def process_vehicle_detection(plate_number, camera_type):
    ist_time = get_ist_time()
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if employee vehicle
    is_employee = employees_col.find_one({"vehicle_number": plate_number}) is not None
    
    # Save to database
    record = {
        "vehicle_number": plate_number,
        "camera": camera_type,
        "timestamp": ist_time,
        "is_employee": is_employee
    }
    
    # Handle entry/exit logic
    if camera_type == "entry":
        # Check for existing exit record without entry
        existing = vehicles_col.find_one({
            "vehicle_number": plate_number,
            "exit_time": {"$exists": True},
            "entry_time": {"$exists": False}
        })
        
        if existing:
            vehicles_col.update_one(
                {"_id": existing["_id"]},
                {"$set": {"entry_time": ist_time, "entry_snapshot": f"snapshots/entry/{plate_number}_{timestamp}.jpg"}}
            )
        else:
            record.update({
                "entry_time": ist_time,
                "exit_time": None,
                "entry_snapshot": f"snapshots/entry/{plate_number}_{timestamp}.jpg"
            })
            vehicles_col.insert_one(record)
    
    elif camera_type == "exit":
        # Find latest entry without exit
        existing = vehicles_col.find_one({
            "vehicle_number": plate_number,
            "entry_time": {"$exists": True},
            "exit_time": {"$exists": False}
        }, sort=[("entry_time", -1)])
        
        if existing:
            vehicles_col.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "exit_time": ist_time,
                    "exit_snapshot": f"snapshots/exit/{plate_number}_{timestamp}.jpg",
                    "camera_exit": camera_type
                }}
            )
        else:
            record.update({
                "entry_time": None,
                "exit_time": ist_time,
                "exit_snapshot": f"snapshots/exit/{plate_number}_{timestamp}.jpg"
            })
            vehicles_col.insert_one(record)
    
    return {
        "vehicle_number": plate_number,
        "camera": camera_type,
        "time": timestamp,
        "is_employee": "Yes" if is_employee else "No",
        "snapshot": record.get("entry_snapshot") or record.get("exit_snapshot")
    }

@app.route('/')
def index():
    current_year = datetime.now().year
    return render_template('index.html', current_year=current_year)

@app.route('/video_feed/<camera_type>')
def video_feed(camera_type):
    camera = entry_camera if camera_type == 'entry' else exit_camera
    return Response(camera.generate_frames(process_vehicle_detection),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_records')
def get_records():
    records = list(vehicles_col.find().sort("timestamp", -1).limit(20))
    result = []
    
    for record in records:
        entry_time = record.get("entry_time")
        exit_time = record.get("exit_time")
        
        result.append({
            "vehicle_number": record["vehicle_number"],
            "camera": record["camera"],
            "entry_time": entry_time.isoformat() if entry_time else "N/A",
            "exit_time": exit_time.isoformat() if exit_time else "N/A",
            "employee": "Yes" if record["is_employee"] else "No"
        })
    
    return jsonify(result)

if __name__ == '__main__':
    # Start camera threads
    entry_thread = threading.Thread(target=entry_camera.start_capture, daemon=True)
    exit_thread = threading.Thread(target=exit_camera.start_capture, daemon=True)
    entry_thread.start()
    exit_thread.start()
    
    app.run(host='0.0.0.0', port=5000, threaded=True)