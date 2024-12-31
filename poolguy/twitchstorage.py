import os
import json
import asyncio
from datetime import datetime

class BaseStorage:
    def save_alert(self, alert_id, alert_data):
        raise NotImplementedError

    def load_alerts(self, date):
        raise NotImplementedError

class JSONStorage(BaseStorage):
    def __init__(self, storage_dir='alerts'):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def save_alert(self, alert_id, alert_data):
        file_path = os.path.join(self.storage_dir, f"{datetime.utcnow().date()}.json")
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    alerts = json.load(f)
            else:
                alerts = {}
        except json.JSONDecodeError:
            alerts = {}
        alerts[str(alert_id)] = alert_data
        with open(file_path, 'w') as f:
            json.dump(alerts, f, indent=4)

    def load_alerts(self, date):
        file_path = os.path.join(self.storage_dir, f"{date}.json")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No alerts found for date {date}")
        with open(file_path, 'r') as f:
            return json.load(f)

class MongoDBStorage(BaseStorage):
    def __init__(self, db_name='twitch_db', collection_name='alerts'):
        try:
            from pymongo import MongoClient
        except ImportError:
            raise ImportError("pymongo is not installed. Please install it to use MongoDBStorage.")
        
        self.client = MongoClient('localhost', 27017)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def save_alert(self, alert_id, alert_data):
        alert_data['_id'] = alert_id
        self.collection.update_one({'_id': alert_id}, {'$set': alert_data}, upsert=True)

    def load_alerts(self, date):
        alerts = self.collection.find({'meta.date': date})
        return {str(alert['_id']): alert for alert in alerts}

class SQLiteStorage(BaseStorage):
    def __init__(self, db_name='twitch_alerts.db'):
        try:
            import sqlite3
        except ImportError:
            raise ImportError("sqlite3 is not installed. Please ensure it is available in your Python environment.")
        
        self.conn = sqlite3.connect(db_name)
        self.create_table()

    def create_table(self):
        query = """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY,
            type TEXT,
            data TEXT,
            meta TEXT
        )
        """
        self.conn.execute(query)
        self.conn.commit()

    def save_alert(self, alert_id, alert_data):
        query = """
        INSERT OR REPLACE INTO alerts (id, type, data, meta)
        VALUES (?, ?, ?, ?)
        """
        self.conn.execute(query, (alert_id, alert_data['type'], json.dumps(alert_data['data']), json.dumps(alert_data['meta'])))
        self.conn.commit()

    def load_alerts(self, date):
        query = """
        SELECT id, type, data, meta FROM alerts WHERE meta LIKE ?
        """
        cursor = self.conn.execute(query, (f'%{date}%',))
        alerts = {}
        for row in cursor:
            alerts[str(row[0])] = {
                'type': row[1],
                'data': json.loads(row[2]),
                'meta': json.loads(row[3])
            }
        return alerts

class StorageFactory:
    @staticmethod
    def create_storage(storage_type, **kwargs):
        if storage_type == 'json':
            return JSONStorage(**kwargs)
        elif storage_type == 'mongodb':
            return MongoDBStorage(**kwargs)
        elif storage_type == 'sqlite':
            return SQLiteStorage(**kwargs)
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")