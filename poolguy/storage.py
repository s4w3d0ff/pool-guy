import os
import re
import json
import logging
import aiosqlite
import aiofiles
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta

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
    async def save_queue(self, queue_data):
        pass

    @abstractmethod
    async def load_queue(self):
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
    
    async def save_queue(self, queue_data):
        file_path = os.path.join(self.storage_dir, "queue.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        saveJSON(queue_data, file_path)

    async def load_queue(self):
        file_path = os.path.join(self.storage_dir, "queue.json")
        if not os.path.exists(file_path):
            logger.warning(f"No queue found at {file_path}")
            return []
        return loadJSON(file_path)

#==================================================================
#==================================================================
class SQLiteStorage(BaseStorage):
    def __init__(self, db_path='db/twitch.db'):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.today = datetime.now(timezone.utc).date()
        self._init_flag = False

    def channel_to_table(self, channel: str) -> str:
        """
        Sanitizes the channel name for use as a SQLite table name.
        Replaces all non-word characters (including .) with underscores.
        """
        name = re.sub(r'\W+', '_', channel)
        return f"{name}"

    async def _execute_async(self, query, params=()):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, params)
            await db.commit()

    async def _init_db(self):
        # Create token and queue tables if they don't exist
        await self._execute_async('''
            CREATE TABLE IF NOT EXISTS tokens (
                name TEXT PRIMARY KEY,
                token_json TEXT
            )
        ''')
        await self._execute_async('''
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_json TEXT
            )
        ''')
        self._init_flag = True

    async def _init_check(self):
        if not self._init_flag:
            await self._init_db()

    async def _ensure_alert_table(self, channel):
        table = self.channel_to_table(channel)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f'''
                CREATE TABLE IF NOT EXISTS {table} (
                    message_id TEXT PRIMARY KEY,
                    data_json TEXT,
                    timestamp TEXT
                )
            ''')
            await db.commit()

    # Token methods
    async def save_token(self, token, name=''):
        await self._init_check()
        token_json = json.dumps(token, indent=4)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT OR REPLACE INTO tokens (name, token_json) VALUES (?, ?)', 
                (name, token_json)
            )
            await db.commit()

    async def load_token(self, name=''):
        await self._init_check()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT token_json FROM tokens WHERE name = ?', (name,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row[0])
                else:
                    logger.warning(f"No token for name: {name}")
                    return None

    # Alert methods
    async def save_alert(self, message_id, channel, data, timestamp):
        await self._init_check()
        table = self.channel_to_table(channel)
        await self._ensure_alert_table(channel)
        if "timestamp" not in data:
            data['timestamp'] = timestamp
        data_json = json.dumps(data, indent=4)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f'INSERT OR REPLACE INTO {table} (message_id, data_json, timestamp) VALUES (?, ?, ?)',
                (str(message_id), data_json, data["timestamp"])
            )
            await db.commit()

    async def load_alerts(self, channel, date=None):
        """
        Returns all alerts for 'channel' where timestamp >= the given date (default: last 30 days).
        'date' can be a datetime.date, datetime.datetime, or 'YYYY-MM-DD' string.
        """
        await self._init_check()
        table = self.channel_to_table(channel)
        await self._ensure_alert_table(channel)

        # Default: last 30 days
        if not date:
            start_dt = datetime.now() - timedelta(days=30)
        elif isinstance(date, str):
            start_dt = datetime.strptime(date, "%Y-%m-%d")
        elif hasattr(date, "year") and hasattr(date, "month") and hasattr(date, "day"):
            # Accepts datetime.date or datetime.datetime
            start_dt = datetime(date.year, date.month, date.day)
        else:
            raise ValueError("date must be None, a 'YYYY-MM-DD' string, or a date/datetime object")

        start_ts = start_dt.timestamp()

        alerts = {}
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f'SELECT message_id, data_json FROM {table} WHERE CAST(timestamp AS REAL) >= ?',
                (start_ts,)
            ) as cursor:
                async for row in cursor:
                    alerts[row[0]] = json.loads(row[1])
        if not alerts:
            logger.warning(f"No alerts found in channel {channel} since {start_dt.date()}")
        return alerts

    async def save_queue(self, queue_data):
        await self._init_check()
        queue_json = json.dumps(queue_data, indent=4)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM queue')
            await db.execute('INSERT INTO queue (queue_json) VALUES (?)', (queue_json,))
            await db.commit()

    async def load_queue(self):
        await self._init_check()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT queue_json FROM queue ORDER BY id DESC LIMIT 1') as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row[0])
                else:
                    logger.warning("No queue found in SQLite DB")
                    return []

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
            case 'sqlite':
                return SQLiteStorage(**kwargs)
            case 'fake':
                return FakeStorage(**kwargs)
            case _:
                logger.error(f"Unknown storage type: {storage_type}!")
                return storage_type(**kwargs)