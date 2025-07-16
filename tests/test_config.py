import pytest
import tempfile
import os
from unittest.mock import patch
import yaml

from src.ocpp_proxy.config import Config


class TestConfig:
    """Unit tests for Config class."""

    @pytest.mark.unit
    def test_config_with_valid_yaml(self):
        """Test loading valid YAML configuration."""
        config_data = {
            'allow_shared_charging': True,
            'preferred_provider': 'test_provider',
            'disallowed_providers': ['bad_provider'],
            'allowed_providers': ['good_provider'],
            'presence_sensor': 'binary_sensor.presence',
            'override_input_boolean': 'input_boolean.override',
            'rate_limit_seconds': 30,
            'ocpp_services': [
                {
                    'id': 'test_service',
                    'url': 'wss://test.com/ocpp',
                    'auth_type': 'token',
                    'token': 'test_token',
                    'enabled': True
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config = Config(config_path)
            assert config.allow_shared_charging == True
            assert config.preferred_provider == 'test_provider'
            assert config.disallowed_providers == ['bad_provider']
            assert config.allowed_providers == ['good_provider']
            assert config.presence_sensor == 'binary_sensor.presence'
            assert config.override_input_boolean == 'input_boolean.override'
            assert config.rate_limit_seconds == 30
            assert len(config.ocpp_services) == 1
            assert config.ocpp_services[0]['id'] == 'test_service'
        finally:
            os.unlink(config_path)

    @pytest.mark.unit
    def test_config_with_missing_file(self):
        """Test config behavior when file doesn't exist."""
        config = Config('/nonexistent/path/config.yaml')
        assert config.allow_shared_charging == False
        assert config.preferred_provider == ''
        assert config.disallowed_providers == []
        assert config.allowed_providers == []
        assert config.presence_sensor == ''
        assert config.override_input_boolean == ''
        assert config.rate_limit_seconds == 10
        assert config.ocpp_services == []

    @pytest.mark.unit
    def test_config_with_empty_file(self):
        """Test config behavior with empty YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('')
            config_path = f.name
        
        try:
            config = Config(config_path)
            assert config.allow_shared_charging == False
            assert config.preferred_provider == ''
            assert config.disallowed_providers == []
            assert config.allowed_providers == []
            assert config.presence_sensor == ''
            assert config.override_input_boolean == ''
            assert config.rate_limit_seconds == 10
            assert config.ocpp_services == []
        finally:
            os.unlink(config_path)

    @pytest.mark.unit
    def test_config_with_partial_data(self):
        """Test config with only some fields present."""
        config_data = {
            'allow_shared_charging': True,
            'rate_limit_seconds': 60
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config = Config(config_path)
            assert config.allow_shared_charging == True
            assert config.preferred_provider == ''
            assert config.disallowed_providers == []
            assert config.allowed_providers == []
            assert config.presence_sensor == ''
            assert config.override_input_boolean == ''
            assert config.rate_limit_seconds == 60
            assert config.ocpp_services == []
        finally:
            os.unlink(config_path)

    @pytest.mark.unit
    def test_config_type_conversion(self):
        """Test that config values are properly converted to expected types."""
        config_data = {
            'allow_shared_charging': 'true',  # string that should convert to bool
            'rate_limit_seconds': '25',       # string that should convert to int
            'preferred_provider': 123,        # int that should convert to string
            'disallowed_providers': ['single_provider'],  # list should stay as list
            'allowed_providers': None,        # None that should convert to list
            'ocpp_services': None            # None that should convert to list
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config = Config(config_path)
            assert config.allow_shared_charging == True
            assert config.rate_limit_seconds == 25
            assert config.preferred_provider == '123'
            assert config.disallowed_providers == ['single_provider']
            assert config.allowed_providers == []
            assert config.ocpp_services == []
        finally:
            os.unlink(config_path)

    @pytest.mark.unit
    @patch.dict(os.environ, {'ADDON_CONFIG_FILE': '/custom/path/config.yaml'})
    def test_config_default_path_from_env(self):
        """Test that default path is loaded from environment variable."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            config = Config()
            # Should use default values when file doesn't exist
            assert config.allow_shared_charging == False

    @pytest.mark.unit
    def test_config_ocpp_services_complex(self):
        """Test complex OCPP services configuration."""
        config_data = {
            'ocpp_services': [
                {
                    'id': 'service1',
                    'url': 'wss://service1.com/ocpp',
                    'auth_type': 'basic',
                    'username': 'user1',
                    'password': 'pass1',
                    'enabled': True
                },
                {
                    'id': 'service2',
                    'url': 'wss://service2.com/ocpp',
                    'auth_type': 'token',
                    'token': 'token123',
                    'enabled': False
                },
                {
                    'id': 'service3',
                    'url': 'wss://service3.com/ocpp',
                    'auth_type': 'none',
                    'enabled': True
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config = Config(config_path)
            services = config.ocpp_services
            assert len(services) == 3
            
            # Check service1
            assert services[0]['id'] == 'service1'
            assert services[0]['auth_type'] == 'basic'
            assert services[0]['username'] == 'user1'
            assert services[0]['password'] == 'pass1'
            assert services[0]['enabled'] == True
            
            # Check service2
            assert services[1]['id'] == 'service2'
            assert services[1]['auth_type'] == 'token'
            assert services[1]['token'] == 'token123'
            assert services[1]['enabled'] == False
            
            # Check service3
            assert services[2]['id'] == 'service3'
            assert services[2]['auth_type'] == 'none'
            assert services[2]['enabled'] == True
        finally:
            os.unlink(config_path)

    @pytest.mark.unit
    def test_config_boolean_values(self):
        """Test various boolean value representations."""
        test_cases = [
            (True, True),
            (False, False),
            (1, True),
            (0, False),
            ('', False),
            (None, False),
            ('non-empty-string', True),  # Any non-empty string is truthy
        ]
        
        for input_val, expected in test_cases:
            config_data = {'allow_shared_charging': input_val}
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config_data, f)
                config_path = f.name
            
            try:
                config = Config(config_path)
                assert config.allow_shared_charging == expected, f"Input {input_val} should convert to {expected}"
            finally:
                os.unlink(config_path)

    @pytest.mark.unit
    def test_config_list_values(self):
        """Test various list value representations."""
        test_cases = [
            (['a', 'b', 'c'], ['a', 'b', 'c']),
            ([], []),
            (None, []),
        ]
        
        for input_val, expected in test_cases:
            config_data = {'disallowed_providers': input_val}
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config_data, f)
                config_path = f.name
            
            try:
                config = Config(config_path)
                assert config.disallowed_providers == expected, f"Input {input_val} should convert to {expected}"
            finally:
                os.unlink(config_path)

    @pytest.mark.unit
    def test_config_string_values(self):
        """Test various string value representations."""
        test_cases = [
            ('test_string', 'test_string'),
            (123, '123'),
            (True, 'True'),
            (False, 'False'),
            ('', '')
        ]
        
        for input_val, expected in test_cases:
            config_data = {'preferred_provider': input_val}
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config_data, f)
                config_path = f.name
            
            try:
                config = Config(config_path)
                assert config.preferred_provider == expected, f"Input {input_val} should convert to {expected}"
            finally:
                os.unlink(config_path)
    
    @pytest.mark.unit
    def test_config_string_none_value(self):
        """Test that None values are handled correctly in string fields."""
        config_data = {'preferred_provider': None}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config = Config(config_path)
            # str(None) returns 'None', but get() with default returns ''
            assert config.preferred_provider == 'None'
        finally:
            os.unlink(config_path)

    @pytest.mark.unit
    def test_config_integer_values(self):
        """Test various integer value representations."""
        test_cases = [
            (10, 10),
            ('15', 15),
            (0, 0),
            (-5, -5),
            ('0', 0)
        ]
        
        for input_val, expected in test_cases:
            config_data = {'rate_limit_seconds': input_val}
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config_data, f)
                config_path = f.name
            
            try:
                config = Config(config_path)
                assert config.rate_limit_seconds == expected, f"Input {input_val} should convert to {expected}"
            finally:
                os.unlink(config_path)

    @pytest.mark.unit
    def test_config_invalid_integer(self):
        """Test config behavior with invalid integer values."""
        config_data = {'rate_limit_seconds': 'invalid_number'}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            config = Config(config_path)
            # Should raise ValueError when trying to convert invalid string to int
            with pytest.raises(ValueError):
                _ = config.rate_limit_seconds
        finally:
            os.unlink(config_path)