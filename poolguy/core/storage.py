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
    def __init__(self, db_path='db/twitch.db'):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def _clean_str(self, text):
        """ Replaces all non-word characters with underscores. """
        out = re.sub(r'\W+', '_', text)
        return f"{out}"

    async def _create_dynamic_table(self, table: str, columns: list[str]):
        column_defs = ', '.join(f"{col} TEXT" for col in columns)
        if self._clean_str(table) in ("tokens", "queue", "subpub_versions"):
            column_defs += ", PRIMARY KEY (name)"
        elif "message_id" in columns:
            column_defs += ", PRIMARY KEY (message_id)"
        else:
            column_defs += f", PRIMARY KEY ({columns[0]})"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"CREATE TABLE IF NOT EXISTS {self._clean_str(table)} ({column_defs});")
            await db.commit()

    async def query(self, table, where=None, params=()):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            sql = f"SELECT * FROM {self._clean_str(table)}"
            sql += f" WHERE {where}" if where else ""
            logger.debug(f"query: {sql = }")
            async with db.execute(sql, params) as cursor:
                return [dict(row) async for row in cursor]

    async def insert(self, table, data: dict, upsert=True):
        d_keys = list(data.keys())
        keys = ', '.join(d_keys)
        placeholders = ', '.join('?' for _ in data)
        updates = ', '.join(f"{k}=excluded.{k}" for k in data)
        if self._clean_str(table) in ("tokens", "queue", "subpub_versions"):
            conflict_col = "name"
        elif "message_id" in data:
            conflict_col = "message_id"
        else:
            conflict_col = d_keys[0]

        sql = f"""
        INSERT INTO {self._clean_str(table)} ({keys}) VALUES ({placeholders})
        ON CONFLICT({conflict_col}) DO UPDATE SET {updates}
        """ if upsert else f"""
        INSERT INTO {self._clean_str(table)} ({keys}) VALUES ({placeholders})
        """
        logger.debug(f"insert: {sql = }")
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
    
    async def delete(self, table, where=None, params=()):
        sql = f"DELETE FROM {self._clean_str(table)}"
        sql += f" WHERE {where}" if where else ""
        logger.debug(f"delete: {sql = }")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(sql, params)
            await db.commit()
    
    async def save_token(self, name, token):
        await self.insert("tokens", {"name": name, "token_json": json.dumps(token)})

    async def get_token(self, name):
        rows = await self.query("tokens", "name = ?", (name,))
        return json.loads(rows[0]["token_json"]) if rows else None
    
    async def load_token(self, name):
        try:
            return await self.get_token(name)
        except:
            return False

    async def save_queue(self, name, queue):
        await self.insert("queue", {"name": name, "queue_json": json.dumps(queue)})

    async def get_queue(self, name):
        rows = await self.query("queue", "name = ?", (name,))
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