from .utils import os, json
from .utils import ColorLogger
from .utils import aioLoadJSON, aioSaveJSON, datetime, timedelta
from abc import ABC, abstractmethod
import glob

logger = ColorLogger(__name__)

class BaseStorage(ABC):
    @abstractmethod
    async def save_alert(self, alert_id, alert_data):
        pass

    @abstractmethod
    async def load_alerts(self, date):
        pass
        
#==================================================================
#==================================================================

class FakeStorage(BaseStorage):
    async def save_alert(self, alert_id, alert_data):
        logger.error(f"[FakeStorage] Fake save_alert triggered!")

    async def load_alerts(self, date):
        logger.error(f"[FakeStorage] Fake load_alerts triggered!")

    async def clean_up(self):
        logger.error(f"[FakeStorage] Fake clean_up triggered!")
 
#==================================================================
#==================================================================

class JSONStorage(BaseStorage):
    def __init__(self, storage_dir='db/alerts', max_days=30*3):
        self.storage_dir = storage_dir
        self.max_days = max_days

    async def save_alert(self, alert_id, alert_data):
        file_path = os.path.join(self.storage_dir, f"{datetime.utcnow().date()}.json")
        try:
            alerts = await aioLoadJSON(file_path) if os.path.exists(file_path) else {}
        except json.JSONDecodeError:
            alerts = {}
        alerts[str(alert_id)] = alert_data
        await aioSaveJSON(alerts, file_path)

    async def load_alerts(self, date):
        file_path = os.path.join(self.storage_dir, f"{date}.json")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No alerts found for date {date}")
        return await aioLoadJSON(file_path)

    async def clean_up(self):
        try:
            # Calculate the cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=self.max_days)
            removed_files = []
            # Get all JSON files in the storage directory
            os.makedirs(self.storage_dir, exist_ok=True)
            json_pattern = os.path.join(self.storage_dir, '*.json')
            for filepath in glob.glob(json_pattern):
                filename = os.path.basename(filepath)
                try:
                    # Parse the date from filename (expects YYYY-MM-DD.json format)
                    file_date = datetime.strptime(filename.split('.')[0], '%Y-%m-%d')
                    # Check if file is older than cutoff date
                    if file_date.date() < cutoff_date.date():
                        os.remove(filepath)
                        removed_files.append(filename)
                        logger.debug(f"Removed old alert file: {filename}")
                except (ValueError, OSError) as e:
                    logger.error(f"Error processing {filename}: {str(e)}")
                    continue
            logger.info(f"Clean up complete. Removed: \n{removed_files}")
            return removed_files

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            raise
        
#==================================================================
#==================================================================

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
        
#==================================================================
#==================================================================

class SQLiteStorage(BaseStorage):
    def __init__(self, db_name='db/alerts/twitch_alerts.db'):
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
        
#==================================================================
#==================================================================

class StorageFactory:
    @staticmethod
    def create_storage(storage_type, **kwargs):
        match storage_type:
            case 'json':
                return JSONStorage(**kwargs)
            case 'mongodb':
                return MongoDBStorage(**kwargs)
            case 'sqlite':
                return SQLiteStorage(**kwargs)
            case 'fake':
                return FakeStorage(**kwargs)
            case _:
                logger.error(f"Unknown storage type: {storage_type}!")
                logger.warning(f"Using 'FakeStorage' instead...")
                return FakeStorage(**kwargs)