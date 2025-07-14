import pytest
import sqlite3
import tempfile
import os
from datetime import datetime
from unittest.mock import patch, Mock

from src.ev_charger_proxy.logger import EventLogger


class TestEventLogger:
    """Unit tests for EventLogger class."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def event_logger(self, temp_db_path):
        """Create an EventLogger instance for testing."""
        return EventLogger(temp_db_path)

    def test_initialization_default_path(self):
        """Test EventLogger initialization with default path."""
        logger = EventLogger()
        assert logger.db_path == 'usage_log.db'
        
        # Cleanup
        if os.path.exists('usage_log.db'):
            os.unlink('usage_log.db')

    def test_initialization_custom_path(self, temp_db_path):
        """Test EventLogger initialization with custom path."""
        logger = EventLogger(temp_db_path)
        assert logger.db_path == temp_db_path

    def test_database_schema_creation(self, event_logger):
        """Test that database schema is created correctly."""
        # Connect to the database and check schema
        conn = sqlite3.connect(event_logger.db_path)
        cursor = conn.cursor()
        
        # Check if sessions table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions';")
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == 'sessions'
        
        # Check table schema
        cursor.execute("PRAGMA table_info(sessions);")
        columns = cursor.fetchall()
        
        expected_columns = [
            ('timestamp', 'TEXT'),
            ('backend_id', 'TEXT'),
            ('duration_s', 'REAL'),
            ('energy_kwh', 'REAL'),
            ('revenue', 'REAL')
        ]
        
        for i, (expected_name, expected_type) in enumerate(expected_columns):
            assert columns[i][1] == expected_name
            assert columns[i][2] == expected_type
        
        conn.close()

    def test_log_session_basic(self, event_logger):
        """Test logging a basic session."""
        event_logger.log_session(
            backend_id='test_backend',
            duration_s=3600.0,
            energy_kwh=25.5,
            revenue=5.10
        )
        
        # Verify the session was logged
        conn = sqlite3.connect(event_logger.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sessions')
        rows = cursor.fetchall()
        
        assert len(rows) == 1
        row = rows[0]
        
        # Check timestamp is recent (within last minute)
        timestamp = datetime.fromisoformat(row[0])
        now = datetime.utcnow()
        assert (now - timestamp).total_seconds() < 60
        
        assert row[1] == 'test_backend'
        assert row[2] == 3600.0
        assert row[3] == 25.5
        assert row[4] == 5.10
        
        conn.close()

    def test_log_multiple_sessions(self, event_logger):
        """Test logging multiple sessions."""
        sessions = [
            ('backend1', 1800.0, 12.5, 2.50),
            ('backend2', 3600.0, 25.0, 5.00),
            ('backend3', 7200.0, 50.0, 10.00),
        ]
        
        for backend_id, duration, energy, revenue in sessions:
            event_logger.log_session(backend_id, duration, energy, revenue)
        
        # Verify all sessions were logged
        conn = sqlite3.connect(event_logger.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT backend_id, duration_s, energy_kwh, revenue FROM sessions ORDER BY backend_id')
        rows = cursor.fetchall()
        
        assert len(rows) == 3
        for i, (backend_id, duration, energy, revenue) in enumerate(sessions):
            assert rows[i][0] == backend_id
            assert rows[i][1] == duration
            assert rows[i][2] == energy
            assert rows[i][3] == revenue
        
        conn.close()

    def test_log_session_with_zero_values(self, event_logger):
        """Test logging session with zero values."""
        event_logger.log_session(
            backend_id='zero_backend',
            duration_s=0.0,
            energy_kwh=0.0,
            revenue=0.0
        )
        
        # Verify the session was logged
        conn = sqlite3.connect(event_logger.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sessions')
        rows = cursor.fetchall()
        
        assert len(rows) == 1
        row = rows[0]
        assert row[1] == 'zero_backend'
        assert row[2] == 0.0
        assert row[3] == 0.0
        assert row[4] == 0.0
        
        conn.close()

    def test_log_session_with_negative_values(self, event_logger):
        """Test logging session with negative values."""
        event_logger.log_session(
            backend_id='negative_backend',
            duration_s=-100.0,
            energy_kwh=-5.0,
            revenue=-1.0
        )
        
        # Verify the session was logged (negative values should be allowed)
        conn = sqlite3.connect(event_logger.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sessions')
        rows = cursor.fetchall()
        
        assert len(rows) == 1
        row = rows[0]
        assert row[1] == 'negative_backend'
        assert row[2] == -100.0
        assert row[3] == -5.0
        assert row[4] == -1.0
        
        conn.close()

    def test_log_session_with_special_characters(self, event_logger):
        """Test logging session with special characters in backend_id."""
        backend_id = 'backend_with_special_chars!@#$%^&*()_+-=[]{}|;:,.<>?'
        
        event_logger.log_session(
            backend_id=backend_id,
            duration_s=3600.0,
            energy_kwh=25.0,
            revenue=5.0
        )
        
        # Verify the session was logged
        conn = sqlite3.connect(event_logger.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT backend_id FROM sessions')
        rows = cursor.fetchall()
        
        assert len(rows) == 1
        assert rows[0][0] == backend_id
        
        conn.close()

    def test_log_session_with_unicode_characters(self, event_logger):
        """Test logging session with unicode characters."""
        backend_id = 'backend_with_unicode_éñ中文🚗⚡'
        
        event_logger.log_session(
            backend_id=backend_id,
            duration_s=3600.0,
            energy_kwh=25.0,
            revenue=5.0
        )
        
        # Verify the session was logged
        conn = sqlite3.connect(event_logger.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT backend_id FROM sessions')
        rows = cursor.fetchall()
        
        assert len(rows) == 1
        assert rows[0][0] == backend_id
        
        conn.close()

    def test_get_sessions_empty(self, event_logger):
        """Test getting sessions from empty database."""
        sessions = event_logger.get_sessions()
        assert sessions == []

    def test_get_sessions_single(self, event_logger):
        """Test getting single session."""
        # Log a session
        event_logger.log_session('test_backend', 3600.0, 25.0, 5.0)
        
        sessions = event_logger.get_sessions()
        assert len(sessions) == 1
        
        session = sessions[0]
        assert session['backend_id'] == 'test_backend'
        assert session['duration_s'] == 3600.0
        assert session['energy_kwh'] == 25.0
        assert session['revenue'] == 5.0
        assert 'timestamp' in session
        
        # Verify timestamp format
        timestamp = datetime.fromisoformat(session['timestamp'])
        assert isinstance(timestamp, datetime)

    def test_get_sessions_multiple(self, event_logger):
        """Test getting multiple sessions."""
        # Log sessions with different timestamps
        sessions_data = [
            ('backend1', 1800.0, 12.5, 2.50),
            ('backend2', 3600.0, 25.0, 5.00),
            ('backend3', 7200.0, 50.0, 10.00),
        ]
        
        for backend_id, duration, energy, revenue in sessions_data:
            event_logger.log_session(backend_id, duration, energy, revenue)
        
        sessions = event_logger.get_sessions()
        assert len(sessions) == 3
        
        # Check all sessions are present
        backend_ids = [session['backend_id'] for session in sessions]
        assert 'backend1' in backend_ids
        assert 'backend2' in backend_ids
        assert 'backend3' in backend_ids

    def test_get_sessions_ordering(self, event_logger):
        """Test that sessions are returned in timestamp order."""
        # Log sessions with slight delays to ensure different timestamps
        import time
        
        event_logger.log_session('first_backend', 1800.0, 12.5, 2.50)
        time.sleep(0.01)
        event_logger.log_session('second_backend', 3600.0, 25.0, 5.00)
        time.sleep(0.01)
        event_logger.log_session('third_backend', 7200.0, 50.0, 10.00)
        
        sessions = event_logger.get_sessions()
        assert len(sessions) == 3
        
        # Check chronological order
        assert sessions[0]['backend_id'] == 'first_backend'
        assert sessions[1]['backend_id'] == 'second_backend'
        assert sessions[2]['backend_id'] == 'third_backend'
        
        # Verify timestamps are in order
        timestamps = [datetime.fromisoformat(session['timestamp']) for session in sessions]
        assert timestamps[0] <= timestamps[1] <= timestamps[2]

    def test_get_sessions_data_structure(self, event_logger):
        """Test the data structure returned by get_sessions."""
        event_logger.log_session('test_backend', 3600.0, 25.0, 5.0)
        
        sessions = event_logger.get_sessions()
        session = sessions[0]
        
        # Check all required fields are present
        required_fields = ['timestamp', 'backend_id', 'duration_s', 'energy_kwh', 'revenue']
        for field in required_fields:
            assert field in session
        
        # Check data types
        assert isinstance(session['timestamp'], str)
        assert isinstance(session['backend_id'], str)
        assert isinstance(session['duration_s'], (int, float))
        assert isinstance(session['energy_kwh'], (int, float))
        assert isinstance(session['revenue'], (int, float))

    def test_export_db_returns_path(self, event_logger):
        """Test that export_db returns the correct database path."""
        db_path = event_logger.export_db()
        assert db_path == event_logger.db_path

    def test_export_db_file_exists(self, event_logger):
        """Test that export_db returns path to existing file."""
        # Log a session to ensure database exists
        event_logger.log_session('test_backend', 3600.0, 25.0, 5.0)
        
        db_path = event_logger.export_db()
        assert os.path.exists(db_path)

    def test_concurrent_logging(self, event_logger):
        """Test concurrent session logging."""
        import threading
        import time
        
        def log_sessions(backend_prefix, count):
            for i in range(count):
                event_logger.log_session(
                    f'{backend_prefix}_{i}',
                    float(i * 100),
                    float(i * 5),
                    float(i * 1.5)
                )
                time.sleep(0.001)  # Small delay to avoid conflicts
        
        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=log_sessions, args=(f'backend{i}', 5))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all sessions were logged
        sessions = event_logger.get_sessions()
        assert len(sessions) == 15  # 3 threads * 5 sessions each

    def test_database_persistence(self, temp_db_path):
        """Test that database persists between EventLogger instances."""
        # Create first logger and log a session
        logger1 = EventLogger(temp_db_path)
        logger1.log_session('test_backend', 3600.0, 25.0, 5.0)
        
        # Create second logger with same path
        logger2 = EventLogger(temp_db_path)
        sessions = logger2.get_sessions()
        
        # Should retrieve the session logged by first logger
        assert len(sessions) == 1
        assert sessions[0]['backend_id'] == 'test_backend'

    def test_database_connection_handling(self, event_logger):
        """Test that database connections are properly handled."""
        # Log multiple sessions
        for i in range(10):
            event_logger.log_session(f'backend_{i}', float(i * 100), float(i * 5), float(i))
        
        # Get sessions multiple times
        for _ in range(5):
            sessions = event_logger.get_sessions()
            assert len(sessions) == 10

    def test_log_session_with_float_precision(self, event_logger):
        """Test logging session with high precision float values."""
        event_logger.log_session(
            backend_id='precision_backend',
            duration_s=3600.123456789,
            energy_kwh=25.987654321,
            revenue=5.12345678901234567890
        )
        
        sessions = event_logger.get_sessions()
        session = sessions[0]
        
        # Check that precision is maintained (within reasonable limits)
        assert abs(session['duration_s'] - 3600.123456789) < 1e-6
        assert abs(session['energy_kwh'] - 25.987654321) < 1e-6
        assert abs(session['revenue'] - 5.12345678901234567890) < 1e-6

    @patch('src.ev_charger_proxy.logger.datetime')
    def test_log_session_timestamp_format(self, mock_datetime, event_logger):
        """Test that timestamp is in correct ISO format."""
        # Mock datetime to return specific time
        mock_now = Mock()
        mock_now.isoformat.return_value = '2023-01-01T12:00:00.123456'
        mock_datetime.datetime.utcnow.return_value = mock_now
        
        event_logger.log_session('test_backend', 3600.0, 25.0, 5.0)
        
        sessions = event_logger.get_sessions()
        assert sessions[0]['timestamp'] == '2023-01-01T12:00:00.123456'

    def test_database_error_handling(self, event_logger):
        """Test handling of database errors."""
        # Close the database file to simulate error
        os.chmod(event_logger.db_path, 0o000)  # Make file unreadable
        
        try:
            # This should raise an exception
            with pytest.raises(sqlite3.OperationalError):
                event_logger.log_session('test_backend', 3600.0, 25.0, 5.0)
        finally:
            # Restore permissions for cleanup
            os.chmod(event_logger.db_path, 0o644)

    def test_large_dataset_performance(self, event_logger):
        """Test performance with larger dataset."""
        import time
        
        # Log many sessions
        start_time = time.time()
        for i in range(1000):
            event_logger.log_session(f'backend_{i}', float(i), float(i * 0.1), float(i * 0.01))
        log_time = time.time() - start_time
        
        # Retrieve sessions
        start_time = time.time()
        sessions = event_logger.get_sessions()
        retrieve_time = time.time() - start_time
        
        assert len(sessions) == 1000
        # Basic performance check (should complete in reasonable time)
        assert log_time < 10.0  # Should log 1000 sessions in under 10 seconds
        assert retrieve_time < 5.0  # Should retrieve 1000 sessions in under 5 seconds