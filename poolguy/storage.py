from .utils import os, json
from .utils import ColorLogger, ABC, abstractmethod
from .utils import aioLoadJSON, aioSaveJSON, datetime, timedelta

logger = ColorLogger(__name__)

class BaseStorage(ABC):
    @abstractmethod
    async def save_alert(self, message_id, channel, data, timestamp):
        pass

    @abstractmethod
    async def load_alerts(self, channel, date):
        pass
        
    @abstractmethod
    async def save_token(self, token, name):
        pass
        
    @abstractmethod
    async def load_token(self, name):
        pass

#==================================================================
#==================================================================
class JSONStorage(BaseStorage):
    def __init__(self, storage_dir='db'):
        self.storage_dir = storage_dir
        # Create base storage directory if it doesn't exist
        os.makedirs(self.storage_dir, exist_ok=True)
        # Create tokens directory
        self.token_dir = os.path.join(self.storage_dir, "tokens")
        os.makedirs(self.token_dir, exist_ok=True)
        # Create alerts directory
        self.alert_dir = os.path.join(self.storage_dir, "alerts")
        os.makedirs(self.alert_dir, exist_ok=True)
        self.today = datetime.utcnow().date()

    async def save_token(self, token, name=''):
        """ Saves OAuth token to database"""
        file_path = os.path.join(self.token_dir, f"{name}.json")
        await aioSaveJSON(token, file_path)

    async def load_token(self, name=''):
        """ Gets saved OAuth token from database"""
        file_path = os.path.join(self.token_dir, f"{name}.json")
        if not os.path.exists(file_path):
            logger.warning(f"No token at: {file_path}")
            return None
        return await aioLoadJSON(file_path)

    async def save_alert(self, message_id, channel, data, timestamp):
        """ Saves an alert to the database """
        alerts = await self.load_alerts(channel)
        if "timestamp" not in data:
            data['timestamp'] = timestamp
        alerts[str(message_id)] = data
        file_path = os.path.join(self.alert_dir, f"{channel}", f"{self.today}.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        await aioSaveJSON(alerts, file_path)

    async def load_alerts(self, channel, date=None):
        """ Loads alerts from <date> """
        if not date:
            date = self.today
        file_path = os.path.join(self.storage_dir, "alerts", f"{channel}", f"{date}.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if not os.path.exists(file_path):
            logger.warning(f"No alerts found at {file_path}")
            return {}
        return await aioLoadJSON(file_path)

#==================================================================
#==================================================================
class MongoDBStorage(BaseStorage):
    async def save_alert(self, message_id, channel, data, timestamp):
        """Save alert to Mongo database"""
        raise NotImplementedError("MongoDBStorage not yet implemented in this version!")

    async def load_alerts(self, channel, date):
        """Load alerts for specific date"""
        raise NotImplementedError("MongoDBStorage not yet implemented in this version!")

    async def save_token(self, token, name):
        """Save OAuth token"""
        raise NotImplementedError("MongoDBStorage not yet implemented in this version!")

    async def load_token(self, name):
        """Load OAuth token"""
        raise NotImplementedError("MongoDBStorage not yet implemented in this version!")
#==================================================================
#==================================================================
class SQLiteStorage(BaseStorage):
    async def save_alert(self, message_id, channel, data, timestamp):
        """Save alert to SQLite database"""
        raise NotImplementedError("SQLiteStorage not yet implemented in this version!")

    async def load_alerts(self, channel, date):
        """Load alerts for specific date"""
        raise NotImplementedError("SQLiteStorage not yet implemented in this version!")

    async def save_token(self, token, name):
        """Save OAuth token"""
        raise NotImplementedError("SQLiteStorage not yet implemented in this version!")

    async def load_token(self, name):
        """Load OAuth token"""
        raise NotImplementedError("SQLiteStorage not yet implemented in this version!")
#==================================================================
#==================================================================
class FakeStorage(BaseStorage):
    async def save_alert(self, message_id, channel, data, timestamp):
        logger.error(f"[FakeStorage] Fake save_alert triggered!")

    async def load_alerts(self, channel, date=None):
        logger.error(f"[FakeStorage] Fake load_alerts triggered!")

    async def save_token(self, token, name):
        logger.error(f"[FakeStorage] Fake save_token triggered!")

    async def load_token(self, name):
        logger.error(f"[FakeStorage] Fake load_token triggered!")
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