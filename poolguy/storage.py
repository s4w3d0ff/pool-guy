from .utils import os, json
from .utils import ColorLogger, ABC, abstractmethod
from .utils import aioLoadJSON, aioSaveJSON, datetime, timedelta

logger = ColorLogger(__name__)

class BaseStorage(ABC):
    @abstractmethod
    async def save_alert(self, alert_id, alert_data):
        pass

    @abstractmethod
    async def load_alerts(self, date):
        pass
        
    @abstractmethod
    async def save_token(self, token, name):
        pass
        
    @abstractmethod
    async def load_token(self, name):
        pass

#==================================================================
#==================================================================

class FakeStorage(BaseStorage):
    async def save_alert(self, alert_id, alert_data):
        logger.error(f"[FakeStorage] Fake save_alert triggered!")

    async def load_alerts(self, date):
        logger.error(f"[FakeStorage] Fake load_alerts triggered!")

    async def save_token(self, token, name):
        logger.error(f"[FakeStorage] Fake save_token triggered!")

    async def load_token(self, name):
        logger.error(f"[FakeStorage] Fake load_token triggered!")

    async def clean_up(self):
        logger.error(f"[FakeStorage] Fake clean_up triggered!")
 
#==================================================================
#==================================================================

class JSONStorage(BaseStorage):
    def __init__(self, storage_dir='db', max_days=30*3):
        self.storage_dir = storage_dir
        self.max_days = max_days

    async def save_token(self, token, name=''):
        """ Saves OAuth token to database"""
        file_path = os.path.join(self.storage_dir, name+"_token.json")
        await aioSaveJSON(token, file_path)

    async def load_token(self, name=''):
        """ Gets saved OAuth token from database"""
        file_path = os.path.join(self.storage_dir, name+"_token.json")
        if not os.path.exists(file_path):
            logger.warning(f"No token at: {file_path}")
            return None
        return await aioLoadJSON(file_path)

    async def save_alert(self, alert_id, alert_data):
        """ Saves an alert to the database """
        file_path = os.path.join(self.storage_dir, f"alerts/{datetime.utcnow().date()}.json")
        try:
            alerts = await aioLoadJSON(file_path) if os.path.exists(file_path) else {}
        except json.JSONDecodeError:
            alerts = {}
        alerts[str(alert_id)] = alert_data
        await aioSaveJSON(alerts, file_path)

    async def load_alerts(self, date):
        """ Loads alerts from <date> """
        file_path = os.path.join(self.storage_dir, f"alerts/{date}.json")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"No alerts found for date {date}")
        return await aioLoadJSON(file_path)

    async def clean_up(self):
        """ Cleans up database """
        try:
            import glob
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
    def __init__(self, db_name='twitch_db', collection_name='alerts', token_collection='tokens', uri='mongodb://localhost:27017/'):
        try:
            from pymongo import MongoClient
            # Initialize MongoDB connection
            self.client = MongoClient(uri)
            self.db = self.client[db_name]
            self.alerts = self.db[collection_name]
            self.tokens = self.db[token_collection]
            # Create indexes for better query performance
            self.alerts.create_index([("date", 1)])
            self.alerts.create_index([("alert_id", 1)])
        except ImportError:
            raise ImportError("pymongo is not installed. Please install it to use MongoDBStorage.")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB connection: {str(e)}")
            raise
        
    async def clean_up(self):
        """Remove alerts older than max_days"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=30*3)  # Default to 90 days
            result = await self.alerts.delete_many({"date": {"$lt": cutoff_date}})
            logger.info(f"Cleaned up {result.deleted_count} old alerts")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            raise
        
    async def save_alert(self, alert_id, alert_data):
        """Save alert to MongoDB"""
        try:
            alert_doc = {
                "alert_id": str(alert_id),
                "data": alert_data,
                "date": datetime.utcnow().date()
            }
            await self.alerts.update_one(
                {"alert_id": str(alert_id)},
                {"$set": alert_doc},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error saving alert: {str(e)}")
            raise

    async def load_alerts(self, date):
        """Load alerts for specific date"""
        try:
            cursor = self.alerts.find(
                {"date": datetime.strptime(str(date), '%Y-%m-%d').date()},
                {"_id": 0, "alert_id": 1, "data": 1}
            )
            alerts = {doc["alert_id"]: doc["data"] async for doc in cursor}
            if not alerts:
                raise FileNotFoundError(f"No alerts found for date {date}")
            return alerts
        except Exception as e:
            logger.error(f"Error loading alerts: {str(e)}")
            raise

    async def save_token(self, token):
        """Save OAuth token"""
        try:
            await self.tokens.update_one(
                {"type": "oauth_token"},
                {"$set": {"token": token, "updated_at": datetime.utcnow()}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error saving token: {str(e)}")
            raise

    async def load_token(self):
        """Load OAuth token"""
        try:
            token_doc = await self.tokens.find_one({"type": "oauth_token"})
            return token_doc["token"] if token_doc else None
        except Exception as e:
            logger.error(f"Error loading token: {str(e)}")
            raise

class SQLiteStorage(BaseStorage):
    def __init__(self, db_name='twitch_alerts.db'):
        try:
            import sqlite3
            import aiosqlite
            self.db_name = db_name
            # Initialize database and create tables
            self._create_tables()
        except ImportError:
            raise ImportError("sqlite3 is not installed. Please ensure it is available in your Python environment.")

    def _create_tables(self):
        """Create necessary tables if they don't exist"""
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    alert_data TEXT,
                    alert_date TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tokens (
                    token_type TEXT PRIMARY KEY,
                    token_data TEXT,
                    updated_at TIMESTAMP
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_alert_date ON alerts(alert_date)')

    async def clean_up(self):
        """Remove alerts older than 90 days"""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=90)).date().isoformat()
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "DELETE FROM alerts WHERE alert_date < ?",
                    (cutoff_date,)
                )
                await db.commit()
                deleted_count = cursor.rowcount
                logger.info(f"Cleaned up {deleted_count} old alerts")
                return deleted_count
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            raise
        
    async def save_alert(self, alert_id, alert_data):
        """Save alert to SQLite database"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO alerts (alert_id, alert_data, alert_date) VALUES (?, ?, ?)",
                    (str(alert_id), json.dumps(alert_data), datetime.utcnow().date().isoformat())
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error saving alert: {str(e)}")
            raise

    async def load_alerts(self, date):
        """Load alerts for specific date"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT alert_id, alert_data FROM alerts WHERE alert_date = ?",
                    (str(date),)
                )
                rows = await cursor.fetchall()
                if not rows:
                    raise FileNotFoundError(f"No alerts found for date {date}")
                return {row['alert_id']: json.loads(row['alert_data']) for row in rows}
        except Exception as e:
            logger.error(f"Error loading alerts: {str(e)}")
            raise

    async def save_token(self, token):
        """Save OAuth token"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO tokens (token_type, token_data, updated_at) VALUES (?, ?, ?)",
                    ('oauth_token', json.dumps(token), datetime.utcnow().isoformat())
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error saving token: {str(e)}")
            raise

    async def load_token(self):
        """Load OAuth token"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT token_data FROM tokens WHERE token_type = ?",
                    ('oauth_token',)
                )
                row = await cursor.fetchone()
                return json.loads(row['token_data']) if row else None
        except Exception as e:
            logger.error(f"Error loading token: {str(e)}")
            raise

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