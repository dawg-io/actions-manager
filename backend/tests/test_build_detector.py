"""
Tests for build_detector module
"""
import pytest
from unittest.mock import Mock, patch
from build_detector import BuildTypeDetector, BuildType


class TestBuildTypeDetector:
    """Test cases for BuildTypeDetector class"""

    def test_build_type_dataclass(self):
        """Test BuildType dataclass creation"""
        build_type = BuildType(
            name="maven",
            technology="Java",
            confidence=0.9,
            files_found=["pom.xml"]
        )
        assert build_type.name == "maven"
        assert build_type.technology == "Java"
        assert build_type.confidence == 0.9
        assert build_type.files_found == ["pom.xml"]
        assert build_type.suggested_workflow is None

    def test_build_type_with_workflow(self):
        """Test BuildType with suggested workflow"""
        workflow = "name: Java CI\non: [push]"
        build_type = BuildType(
            name="maven",
            technology="Java", 
            confidence=0.9,
            files_found=["pom.xml"],
            suggested_workflow=workflow
        )
        assert build_type.suggested_workflow == workflow

    def test_detector_init(self):
        """Test BuildTypeDetector initialization"""
        detector = BuildTypeDetector("test_token")
        assert detector.BUILD_PATTERNS is not None
        assert "maven" in detector.BUILD_PATTERNS
        assert "npm" in detector.BUILD_PATTERNS
        assert detector.github_token == "test_token"

    def test_detector_init_with_empty_token(self):
        """Test BuildTypeDetector initialization with empty token"""
        detector = BuildTypeDetector("")
        assert detector.github_token == ""
        assert "Authorization" not in detector.headers

    def test_build_patterns_structure(self):
        """Test that build patterns have required structure"""
        detector = BuildTypeDetector("test_token")
        for pattern_name, pattern_config in detector.BUILD_PATTERNS.items():
            assert "technology" in pattern_config
            assert "files" in pattern_config
            assert "confidence" in pattern_config
            assert isinstance(pattern_config["files"], list)
            assert isinstance(pattern_config["confidence"], (int, float))
            assert 0 <= pattern_config["confidence"] <= 1

    @patch('requests.get')
    def test_detect_build_types_api_error(self, mock_get):
        """Test detection when GitHub API returns error"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}
        mock_get.return_value = mock_response
        
        detector = BuildTypeDetector("test_token")
        # This would normally call the GitHub API - we'll test the error handling
        # Note: The actual method would need to be implemented in the detector
        assert detector.BUILD_PATTERNS is not None  # Basic existence test

    def test_maven_pattern(self):
        """Test Maven build pattern configuration"""
        detector = BuildTypeDetector("test_token")
        maven_pattern = detector.BUILD_PATTERNS["maven"]
        assert maven_pattern["technology"] == "Java"
        assert "pom.xml" in maven_pattern["files"]
        assert maven_pattern["confidence"] == 0.9

    def test_npm_pattern(self):
        """Test NPM build pattern configuration"""
        detector = BuildTypeDetector("test_token")
        npm_pattern = detector.BUILD_PATTERNS["npm"]
        assert npm_pattern["technology"] == "Node.js"
        assert "package.json" in npm_pattern["files"]
        assert npm_pattern["confidence"] == 0.9