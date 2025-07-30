import os
import re
import json
import logging
import aiofiles
import aiosqlite
import sqlite3

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

#==================================================================
#==================================================================
class SQLiteStorage:

    TABLE_SCHEMAS = {
        "tokens": ["name", "token_json"],
        "queue": ["name", "queue_json"],
        "subpub_versions": ["name", "version"],
        #"stream_online": ["message_id", "timestamp", "type", "id"],
        #"channel_bits_use": ["message_id", "timestamp", "user_id", "user_login", "bits", "type", "message"],
        #"channel_channel_points_custom_reward_redemption_add": ["message_id", "timestamp", "user_id", "user_login", "user_input", "reward_id", "title", "cost", "prompt"],
        #"channel_ban": ["message_id", "timestamp", "user_id", "user_login", "moderator_user_id", "moderator_user_login", "reason", "ends_at"],
        #"channel_chat_notification": ["message_id", "timestamp", "notice_type", "chatter_user_id", "chatter_user_login", "chatter_is_anonymous", "color", "data"],
        #"channel_follow": ["message_id", "timestamp", "user_id", "user_login"],
        #"channel_hype_train_end": ["message_id", "timestamp", "total", "is_golden_kappa_train", "level", "cooldown_ends_at", "top_contributions"],
        #"channel_prediction_end": ["message_id", "timestamp", "title", "outcomes", "winning_outcome_id", "status"],
        #"channel_suspicious_user_message": ["message_id", "timestamp", "user_id", "user_login", "low_trust_status", "shared_ban_channel_ids", "types", "ban_evasion_evaluation", "message"]
    }

    def __init__(self, db_path='db/twitch.db'):
        self.db_path = db_path
        self._init_flag = False
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def channel_to_table(self, channel):
        """
        Sanitizes the channel name for use as a SQLite table name.
        Replaces all non-word characters (including .) with underscores.
        """
        name = re.sub(r'\W+', '_', channel)
        return f"{name}"

    async def _init_check(self):
        if not self._init_flag:
            await self._init_db()
            self._init_flag = True

    async def _init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            for table, columns in self.TABLE_SCHEMAS.items():
                column_defs = ', '.join(f"{col} TEXT" for col in columns)
                # Primary key on 'name' for tokens and queue tables
                if table in ("tokens", "queue", "subpub_versions"):
                    column_defs += ", PRIMARY KEY (name)"
                else:
                    column_defs += ", PRIMARY KEY (message_id)"
                await db.execute(f"CREATE TABLE IF NOT EXISTS {table} ({column_defs});")
            await db.commit()

    async def _create_dynamic_table(self, table: str, columns: list[str]):
        column_defs = ', '.join(f"{col} TEXT" for col in columns)
        # Use "message_id" or "name" if present, otherwise fallback to first column
        if "message_id" in columns:
            column_defs += ", PRIMARY KEY (message_id)"
        elif "name" in columns:
            column_defs += ", PRIMARY KEY (name)"
        else:
            column_defs += f", PRIMARY KEY ({columns[0]})"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"CREATE TABLE IF NOT EXISTS {table} ({column_defs});")
            await db.commit()

    async def query(self, table, where="", params=()):
        await self._init_check()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            sql = f"SELECT * FROM {table} {where}"
            async with db.execute(sql, params) as cursor:
                return [dict(row) async for row in cursor]


    async def insert(self, table, data: dict, upsert=True):
        await self._init_check()
        keys = ', '.join(data.keys())
        placeholders = ', '.join('?' for _ in data)
        updates = ', '.join(f"{k}=excluded.{k}" for k in data)

        conflict_col = "name" if table in ("tokens", "queue", "subpub_versions") else "message_id"

        sql = f"""
        INSERT INTO {table} ({keys}) VALUES ({placeholders})
        ON CONFLICT({conflict_col}) DO UPDATE SET {updates}
        """ if upsert else f"""
        INSERT INTO {table} ({keys}) VALUES ({placeholders})
        """

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(sql, tuple(data.values()))
                await db.commit()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                await self._create_dynamic_table(table, list(data.keys()))
                # Retry the insert
                await self.insert(table, data, upsert)
            else:
                raise


    async def save_token(self, name, token):
        await self.insert("tokens", {"name": name, "token_json": json.dumps(token)})

    async def get_token(self, name):
        rows = await self.query("tokens", "WHERE name = ?", (name,))
        return json.loads(rows[0]["token_json"]) if rows else None
    
    async def load_token(self, name):
        return await self.get_token(name)

    async def save_queue(self, name, queue):
        await self.insert("queue", {"name": name, "queue_json": json.dumps(queue)})

    async def get_queue(self, name):
        rows = await self.query("queue", "WHERE name = ?", (name,))
        return json.loads(rows[0]["queue_json"]) if rows else None

    async def load_queue(self, name):
        return await self.get_queue(name)
    


#==================================================================
#==================================================================
class StorageFactory:
    @staticmethod
    def create_storage(storage_type='sqlite', **kwargs):
        match storage_type:
            case 'sqlite':
                return SQLiteStorage(**kwargs)
            case _:
                logger.error(f"Unknown storage type: {storage_type}!")
                return storage_type(**kwargs)