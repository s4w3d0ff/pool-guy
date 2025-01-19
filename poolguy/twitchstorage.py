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
        
    @abstractmethod
    async def save_token(self, token):
        pass
        
    @abstractmethod
    async def load_token(self):
        pass

#==================================================================
#==================================================================

class FakeStorage(BaseStorage):
    async def save_alert(self, alert_id, alert_data):
        logger.error(f"[FakeStorage] Fake save_alert triggered!")

    async def load_alerts(self, date):
        logger.error(f"[FakeStorage] Fake load_alerts triggered!")

    async def save_token(self, token):
        logger.error(f"[FakeStorage] Fake save_token triggered!")

    async def load_token(self):
        logger.error(f"[FakeStorage] Fake load_token triggered!")

    async def clean_up(self):
        logger.error(f"[FakeStorage] Fake clean_up triggered!")
 
#==================================================================
#==================================================================

class JSONStorage(BaseStorage):
    def __init__(self, storage_dir='db', max_days=30*3):
        self.storage_dir = storage_dir
        self.max_days = max_days

    async def save_token(self, token):
        file_path = os.path.join(self.storage_dir, "token.json")
        await aioSaveJSON(token, file_path)

    async def load_token(self):
        file_path = os.path.join(self.storage_dir, "token.json")
        if not os.path.exists(file_path):
            logger.warning(f"No token.json found")
            return False
        return await aioLoadJSON(file_path)

    async def save_alert(self, alert_id, alert_data):
        file_path = os.path.join(self.storage_dir, f"alerts/{datetime.utcnow().date()}.json")
        try:
            alerts = await aioLoadJSON(file_path) if os.path.exists(file_path) else {}
        except json.JSONDecodeError:
            alerts = {}
        alerts[str(alert_id)] = alert_data
        await aioSaveJSON(alerts, file_path)

    async def load_alerts(self, date):
        file_path = os.path.join(self.storage_dir, f"alerts/{date}.json")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No alerts found for date {date}")
        return await aioLoadJSON(file_path)

    async def clean_up(self):
        try:
            # Calculate the cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=self.max_days)
            removed_files = []
            # Get all JSON files in the storage directory
            os.makedirs(self.storage_dir+'/alerts', exist_ok=True)
            json_pattern = os.path.join(self.storage_dir, 'alerts/'+'*.json')
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
        
    def create_table(self):
        pass
        
    def save_alert(self, alert_id, alert_data):
        pass

    def load_alerts(self, date):
        pass

    async def save_token(self, token):
        pass

    async def load_token(self):
        pass
        
#==================================================================
#==================================================================

class SQLiteStorage(BaseStorage):
    def __init__(self, db_name='twitch_alerts.db'):
        try:
            import sqlite3
        except ImportError:
            raise ImportError("sqlite3 is not installed. Please ensure it is available in your Python environment.")

    async def create_table(self):
        pass
        
    async def save_alert(self, alert_id, alert_data):
        pass

    async def load_alerts(self, date):
        pass

    async def save_token(self, token):
        pass

    async def load_token(self):
        pass

#==================================================================
#==================================================================

class StorageFactory:
    @staticmethod
    def create_storage(storage_type='json', **kwargs):
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