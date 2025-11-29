from pymongo import MongoClient
import os
import json

# MongoDB connection settings
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27018')
DB_NAME = os.getenv('MONGO_DB_NAME', 'mydatabase')

def update_mongodb_documents():
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db.devices_device

        # Update documents that don't have command_history
        result1 = collection.update_many(
            {"command_history": {"$exists": False}},
            {"$set": {"command_history": json.dumps([])}}
        )
        print(f"Updated {result1.modified_count} documents for command_history")

        # Update documents that don't have scheduled_commands
        result2 = collection.update_many(
            {"scheduled_commands": {"$exists": False}},
            {"$set": {"scheduled_commands": json.dumps([])}}
        )
        print(f"Updated {result2.modified_count} documents for scheduled_commands")

        # Fix any existing documents that might have lists instead of JSON strings
        result3 = collection.update_many(
            {"command_history": {"$type": "array"}},
            [{"$set": {"command_history": {"$toString": "$command_history"}}}]
        )
        print(f"Fixed {result3.modified_count} documents with array command_history")

        result4 = collection.update_many(
            {"scheduled_commands": {"$type": "array"}},
            [{"$set": {"scheduled_commands": {"$toString": "$scheduled_commands"}}}]
        )
        print(f"Fixed {result4.modified_count} documents with array scheduled_commands")

        print("MongoDB update completed successfully!")
    except Exception as e:
        print(f"Error updating MongoDB: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    update_mongodb_documents() 