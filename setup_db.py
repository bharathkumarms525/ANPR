from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client['vehicle_management']

# Create collections
vehicles_col = db['vehicles']
employees_col = db['employee_vehicles']

# Create indexes
vehicles_col.create_index("vehicle_number")
vehicles_col.create_index("timestamp")
employees_col.create_index("vehicle_number")

# Sample employee vehicles
sample_employees = [
    {"vehicle_number": "MH01AB1234"},
    {"vehicle_number": "DL02CD5678"},
    {"vehicle_number": "KA03EF9012"}
]

# Insert sample data (only if collection is empty)
if employees_col.count_documents({}) == 0:
    employees_col.insert_many(sample_employees)
    print("Sample employee vehicles inserted")

print("Database setup complete!")