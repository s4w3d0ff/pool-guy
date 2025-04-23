import os
import json
import logging
import aiofiles
from abc import ABC, abstractmethod
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def loadJSON(filename):
    """ Load json file """
    with open(filename, 'r') as f:
        out = json.load(f)
        logger.debug(f"[loadJSON] {filename}")
        return out

def saveJSON(data, filename, str_fmat=False):
    """ Save data as json to a file """
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
        logger.debug(f"[saveJSON] {filename}")

async def aioUpdateFile(file_path, text):
    async with aiofiles.open(file_path, "w") as file:
        await file.write(text)
        logger.debug(f"[aioUpdateFile] {file_path}")

async def aioLoadJSON(filename):
    async with aiofiles.open(filename, 'r') as file:
        content = await file.read()
        return json.loads(content)

async def aioSaveJSON(data, filename):
    async with aiofiles.open(filename, 'w') as file:
        await file.write(json.dumps(data, indent=4))

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

    @abstractmethod
    def save_queue(self, queue_data):
        pass

    @abstractmethod
    def load_queue(self):
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
        self.today = datetime.now(timezone.utc).date()

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
    
    def save_queue(self, queue_data):
        file_path = os.path.join(self.storage_dir, "queue.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        saveJSON(queue_data, file_path)

    def load_queue(self):
        file_path = os.path.join(self.storage_dir, "queue.json")
        if not os.path.exists(file_path):
            logger.warning(f"No queue found at {file_path}")
            return []
        return loadJSON(file_path)

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
                return storage_type(**kwargs)