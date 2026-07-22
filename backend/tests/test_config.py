"""
Tests for config.py module
"""
import pytest
import os
import sys

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestInstallationMode:
    """Test class for INSTALLATION_MODE configuration"""
    
    def test_default_mode_when_not_set(self, monkeypatch):
        """Test that default mode is 'self-hosted' when INSTALLATION_MODE is not set"""
        monkeypatch.delenv("INSTALLATION_MODE", raising=False)
        
        # Need to reload the module to pick up the new environment
        import importlib
        import config
        importlib.reload(config)
        
        assert config.INSTALLATION_MODE == "self-hosted"
        assert config.get_installation_mode() == "self-hosted"
    
    def test_default_mode_when_empty_string(self, monkeypatch):
        """Test that default mode is 'self-hosted' when INSTALLATION_MODE is empty string"""
        monkeypatch.setenv("INSTALLATION_MODE", "")
        
        import importlib
        import config
        importlib.reload(config)
        
        assert config.INSTALLATION_MODE == "self-hosted"
        assert config.get_installation_mode() == "self-hosted"
    
    def test_default_mode_when_whitespace(self, monkeypatch):
        """Test that default mode is 'self-hosted' when INSTALLATION_MODE is whitespace"""
        monkeypatch.setenv("INSTALLATION_MODE", "   ")
        
        import importlib
        import config
        importlib.reload(config)
        
        assert config.INSTALLATION_MODE == "self-hosted"
        assert config.get_installation_mode() == "self-hosted"
    
    def test_cloud_mode(self, monkeypatch):
        """Test that 'cloud' mode is properly recognized"""
        monkeypatch.setenv("INSTALLATION_MODE", "cloud")
        
        import importlib
        import config
        importlib.reload(config)
        
        assert config.INSTALLATION_MODE == "cloud"
        assert config.get_installation_mode() == "cloud"
    
    def test_cloud_mode_case_insensitive(self, monkeypatch):
        """Test that 'cloud' mode is case insensitive"""
        monkeypatch.setenv("INSTALLATION_MODE", "CLOUD")
        
        import importlib
        import config
        importlib.reload(config)
        
        assert config.INSTALLATION_MODE == "cloud"
        assert config.get_installation_mode() == "cloud"
    
    def test_self_hosted_mode(self, monkeypatch):
        """Test that 'self-hosted' mode is properly recognized"""
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        
        import importlib
        import config
        importlib.reload(config)
        
        assert config.INSTALLATION_MODE == "self-hosted"
        assert config.get_installation_mode() == "self-hosted"
    
    def test_self_hosted_mode_case_insensitive(self, monkeypatch):
        """Test that 'self-hosted' mode is case insensitive"""
        monkeypatch.setenv("INSTALLATION_MODE", "Self-Hosted")
        
        import importlib
        import config
        importlib.reload(config)
        
        assert config.INSTALLATION_MODE == "self-hosted"
        assert config.get_installation_mode() == "self-hosted"
    
    def test_invalid_mode_raises_error(self, monkeypatch):
        """Test that invalid mode raises ValueError"""
        monkeypatch.setenv("INSTALLATION_MODE", "invalid")
        
        import importlib
        import config
        
        with pytest.raises(ValueError) as exc_info:
            importlib.reload(config)
        
        assert "Invalid INSTALLATION_MODE: 'invalid'" in str(exc_info.value)
        assert "Must be one of:" in str(exc_info.value)
        assert "cloud" in str(exc_info.value)
        assert "self-hosted" in str(exc_info.value)
    
    def test_typo_mode_raises_error(self, monkeypatch):
        """Test that typo in mode raises ValueError"""
        monkeypatch.setenv("INSTALLATION_MODE", "clound")
        
        import importlib
        import config
        
        with pytest.raises(ValueError) as exc_info:
            importlib.reload(config)
        
        assert "Invalid INSTALLATION_MODE: 'clound'" in str(exc_info.value)
    
    def test_another_typo_mode_raises_error(self, monkeypatch):
        """Test that another typo in mode raises ValueError"""
        monkeypatch.setenv("INSTALLATION_MODE", "self-host")
        
        import importlib
        import config
        
        with pytest.raises(ValueError) as exc_info:
            importlib.reload(config)
        
        assert "Invalid INSTALLATION_MODE: 'self-host'" in str(exc_info.value)
    
    def test_valid_modes_constant(self):
        """Test that VALID_MODES contains expected values"""
        import config
        
        assert config.VALID_MODES == {"cloud", "self-hosted"}
    
    def test_default_mode_constant(self):
        """Test that DEFAULT_MODE is 'self-hosted'"""
        import config
        
        assert config.DEFAULT_MODE == "self-hosted"
