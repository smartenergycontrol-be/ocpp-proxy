import sqlite3
import datetime


class EventLogger:
    """
    Track charger sessions and revenue, persist in SQLite.
    """

    def __init__(self, db_path: str = 'usage_log.db'):
        self.db_path = db_path
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                timestamp TEXT,
                backend_id TEXT,
                duration_s REAL,
                energy_kwh REAL,
                revenue REAL
            )
        ''')
        conn.commit()
        conn.close()

    def log_session(
        self,
        backend_id: str,
        duration_s: float,
        energy_kwh: float,
        revenue: float
    ) -> None:
        """Persist a session record into SQLite."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO sessions (timestamp, backend_id, duration_s, energy_kwh, revenue) '
            'VALUES (?, ?, ?, ?, ?)',
            (datetime.datetime.utcnow().isoformat(),
             backend_id, duration_s, energy_kwh, revenue)
        )
        conn.commit()
        conn.close()

    def get_sessions(self) -> list:
        """Fetch all logged sessions as list of dicts."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT timestamp, backend_id, duration_s, energy_kwh, revenue '
            'FROM sessions ORDER BY timestamp'
        )
        rows = cursor.fetchall()
        conn.close()

        sessions = []
        for ts, backend, dur, energy, rev in rows:
            sessions.append({
                'timestamp': ts,
                'backend_id': backend,
                'duration_s': dur,
                'energy_kwh': energy,
                'revenue': rev,
            })
        return sessions

    def export_db(self) -> str:
        """Return path to the SQLite database file."""
        return self.db_path
