"""
QA Test Suite for Docker Deployment Validation

This test suite validates:
1. Docker-compose configurations (self-hosted and cloud)
2. Environment variable handling
3. Installation script functionality
4. Deployment health checks
5. Common error scenarios

Acceptance Criteria:
- Both compose files work correctly
- Environment variables are properly loaded
- Health checks pass
"""

import pytest
import os
import sys
import yaml
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Repository root directory
REPO_ROOT = Path(__file__).parent.parent.parent.absolute()


class TestDockerComposeConfigurations:
    """Test docker-compose file configurations"""
    
    def test_self_hosted_compose_file_exists(self):
        """Verify self-hosted docker-compose file exists"""
        compose_file = REPO_ROOT / "docker-compose.self-hosted.yml"
        assert compose_file.exists(), "docker-compose.self-hosted.yml not found"
    
    def test_cloud_compose_file_exists(self):
        """Verify cloud docker-compose file exists"""
        compose_file = REPO_ROOT / "docker-compose.cloud.yml"
        assert compose_file.exists(), "docker-compose.cloud.yml not found"
    
    def test_self_hosted_compose_valid_yaml(self):
        """Verify self-hosted compose file is valid YAML"""
        compose_file = REPO_ROOT / "docker-compose.self-hosted.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        assert config is not None
        assert 'services' in config
    
    def test_cloud_compose_valid_yaml(self):
        """Verify cloud compose file is valid YAML"""
        compose_file = REPO_ROOT / "docker-compose.cloud.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        assert config is not None
        assert 'services' in config
    
    def test_self_hosted_has_app_service(self):
        """Verify self-hosted compose has app service.

        The official self-hosted release pulls a pre-built single-container
        image from GHCR (ghcr.io/dawg-io/actions-manager/self-hosted), so
        the compose file must declare an ``image:`` reference. Contributors
        who want to build from source layer ``docker-compose.self-hosted.dev.yml``
        on top, which adds the ``build:`` directive.
        """
        compose_file = REPO_ROOT / "docker-compose.self-hosted.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)

        assert 'app' in config['services']
        app_config = config['services']['app']
        assert 'image' in app_config, (
            "Self-hosted release flow must pull a pre-built image from GHCR; "
            "set `image:` in docker-compose.self-hosted.yml"
        )
        # The compose file uses env-var indirection so operators can override
        # the registry/tag. Match the default GHCR path with a regex against
        # the dotenv-style template — this is *not* URL sanitization.
        import re as _re
        assert _re.search(
            r"ghcr\.io/dawg-io/actions-manager/self-hosted",
            app_config['image'],
        ), (
            "Self-hosted image must default to the official "
            "ghcr.io/dawg-io/actions-manager/self-hosted GHCR image"
        )
        assert 'ports' in app_config
        assert 'env_file' in app_config

        # The contributor build overlay must still exist for local development.
        dev_overlay = REPO_ROOT / "docker-compose.self-hosted.dev.yml"
        assert dev_overlay.exists(), (
            "Contributors must still be able to build from source via "
            "docker-compose.self-hosted.dev.yml"
        )
        with open(dev_overlay, 'r') as f:
            dev_config = yaml.safe_load(f)
        assert 'build' in dev_config['services']['app'], (
            "Dev overlay must define a `build:` directive so contributors "
            "can build the image from local source"
        )
    
    def test_cloud_has_backend_and_frontend_services(self):
        """Verify cloud compose has backend and frontend services"""
        compose_file = REPO_ROOT / "docker-compose.cloud.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        assert 'backend' in config['services']
        assert 'frontend' in config['services']
    
    def test_self_hosted_port_configuration(self):
        """Verify self-hosted exposes correct port"""
        compose_file = REPO_ROOT / "docker-compose.self-hosted.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        ports = config['services']['app']['ports']
        assert '8080:8080' in ports or any('8080' in p for p in ports)
    
    def test_cloud_port_configuration(self):
        """Verify cloud exposes correct ports"""
        compose_file = REPO_ROOT / "docker-compose.cloud.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        backend_ports = config['services']['backend']['ports']
        frontend_ports = config['services']['frontend']['ports']
        
        assert '8000:8000' in backend_ports or any('8000' in p for p in backend_ports)
        assert '3000:3000' in frontend_ports or any('3000' in p for p in frontend_ports)
    
    def test_self_hosted_healthcheck_configured(self):
        """Verify self-hosted has health check configured"""
        compose_file = REPO_ROOT / "docker-compose.self-hosted.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        assert 'healthcheck' in config['services']['app']
        healthcheck = config['services']['app']['healthcheck']
        assert 'test' in healthcheck
        assert 'interval' in healthcheck
    
    def test_cloud_healthcheck_configured(self):
        """Verify cloud has health checks configured"""
        compose_file = REPO_ROOT / "docker-compose.cloud.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        assert 'healthcheck' in config['services']['backend']
    
    def test_self_hosted_environment_mode_set(self):
        """Verify self-hosted sets INSTALLATION_MODE=self-hosted"""
        compose_file = REPO_ROOT / "docker-compose.self-hosted.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        env = config['services']['app'].get('environment', [])
        has_self_hosted = any('INSTALLATION_MODE=self-hosted' in str(e) for e in env)
        assert has_self_hosted, "Self-hosted mode not configured"
    
    def test_cloud_environment_mode_set(self):
        """Verify cloud sets INSTALLATION_MODE=cloud"""
        compose_file = REPO_ROOT / "docker-compose.cloud.yml"
        with open(compose_file, 'r') as f:
            config = yaml.safe_load(f)
        
        env = config['services']['backend'].get('environment', [])
        has_cloud = any('INSTALLATION_MODE=cloud' in str(e) for e in env)
        assert has_cloud, "Cloud mode not configured"


class TestEnvironmentFiles:
    """Test environment file templates"""
    
    def test_self_hosted_env_example_exists(self):
        """Verify .env.self-hosted.example exists"""
        env_file = REPO_ROOT / ".env.self-hosted.example"
        assert env_file.exists(), ".env.self-hosted.example not found"
    
    def test_cloud_env_example_exists(self):
        """Verify .env.cloud.example exists"""
        env_file = REPO_ROOT / ".env.cloud.example"
        assert env_file.exists(), ".env.cloud.example not found"
    
    def test_self_hosted_env_has_required_variables(self):
        """Verify self-hosted env example has all required variables.

        Admin credentials are NOT required in self-hosted mode since:
        1. OAuth is the primary authentication method
        2. Admin panel is cloud-only (admin.py is removed from self-hosted images)
        3. Self-hosted operators typically use OAuth and don't need local admin users
        
        URL configuration: APP_URL is the primary simplified config.
        VITE_APP_URL is a deprecated alias still accepted by start.sh.
        VITE_BACKEND_URL / VITE_FRONTEND_URL / VITE_WEBSOCKET_URL are the
        explicit per-service overrides. Legacy REACT_APP_* names are still
        accepted by start.sh as deprecated fallbacks.
        """
        env_file = REPO_ROOT / ".env.self-hosted.example"
        with open(env_file, 'r') as f:
            content = f.read()

        required_vars = [
            'INSTALLATION_MODE',
            'GITHUB_CLIENT_ID',
            'GITHUB_CLIENT_SECRET',
            # APP_URL is the primary all-in-one self-hosted config
            'APP_URL',
            # Explicit per-service overrides (documented as advanced options)
            'VITE_BACKEND_URL',
            'VITE_FRONTEND_URL',
        ]

        for var in required_vars:
            assert var in content, f"Required variable {var} not in .env.self-hosted.example"

        # Admin credentials should NOT be in self-hosted template
        # (admin panel is cloud-only)
        assert 'ADMIN_USERNAME' not in content, (
            "ADMIN_USERNAME should not be in self-hosted template - "
            "admin panel is cloud-only"
        )
        assert 'ADMIN_PASSWORD' not in content, (
            "ADMIN_PASSWORD should not be in self-hosted template - "
            "admin panel is cloud-only"
        )
    
    def test_self_hosted_env_has_license_fields(self):
        """Verify self-hosted env example has license key guidance"""
        env_file = REPO_ROOT / ".env.self-hosted.example"
        with open(env_file, 'r') as f:
            content = f.read()
        
        content_lower = content.lower()
        assert 'LICENSE_KEY' in content
        assert 'no license_secret is required' in content_lower or 'no signing secret is required' in content_lower
    
    def test_cloud_env_has_required_variables(self):
        """Verify cloud env example has all required variables"""
        env_file = REPO_ROOT / ".env.cloud.example"
        with open(env_file, 'r') as f:
            content = f.read()
        
        required_vars = [
            'INSTALLATION_MODE',
            'DATABASE_URL',
            'GITHUB_WEBHOOK_SECRET'
        ]
        
        for var in required_vars:
            assert var in content, f"Required variable {var} not in .env.cloud.example"


class TestInstallScript:
    """Test install.sh script functionality"""
    
    def test_install_script_exists(self):
        """Verify install.sh exists"""
        install_script = REPO_ROOT / "install.sh"
        assert install_script.exists(), "install.sh not found"
    
    def test_install_script_is_executable(self):
        """Verify install.sh has execute permissions"""
        install_script = REPO_ROOT / "install.sh"
        assert os.access(install_script, os.X_OK), "install.sh is not executable"
    
    def test_install_script_has_shebang(self):
        """Verify install.sh has proper shebang"""
        install_script = REPO_ROOT / "install.sh"
        with open(install_script, 'r') as f:
            first_line = f.readline().strip()
        
        assert first_line.startswith('#!/'), "install.sh missing shebang"
    
    def test_install_script_checks_docker(self):
        """Verify install.sh checks for Docker/Podman"""
        install_script = REPO_ROOT / "install.sh"
        with open(install_script, 'r') as f:
            content = f.read()
        
        assert 'check_docker' in content or 'docker' in content.lower()
    
    def test_install_script_prompts_for_github_oauth(self):
        """Verify install.sh prompts for GitHub OAuth"""
        install_script = REPO_ROOT / "install.sh"
        with open(install_script, 'r') as f:
            content = f.read()
        
        assert 'GITHUB_CLIENT_ID' in content
        assert 'GITHUB_CLIENT_SECRET' in content
    
    def test_install_script_prompts_for_license(self):
        """Verify install.sh prompts for license key without customer signing secrets"""
        install_script = REPO_ROOT / "install.sh"
        with open(install_script, 'r') as f:
            content = f.read()
        
        assert 'LICENSE_KEY' in content
        assert 'License Secret' not in content
    
    def test_install_script_has_troubleshooting_section(self):
        """Verify install.sh includes troubleshooting"""
        install_script = REPO_ROOT / "install.sh"
        with open(install_script, 'r') as f:
            content = f.read()
        
        assert 'troubleshooting' in content.lower() or 'error' in content.lower()
    
    def test_install_script_generates_secret_key(self):
        """Verify install.sh generates SECRET_KEY"""
        install_script = REPO_ROOT / "install.sh"
        with open(install_script, 'r') as f:
            content = f.read()
        
        assert 'SECRET_KEY' in content
        assert 'generate' in content.lower() or 'openssl' in content or 'random' in content.lower()


class TestDockerfile:
    """Test Dockerfile configurations"""
    
    def test_self_hosted_dockerfile_exists(self):
        """Verify self-hosted Dockerfile exists"""
        dockerfile = REPO_ROOT / "Dockerfile.self-hosted"
        assert dockerfile.exists(), "Dockerfile.self-hosted not found"
    
    def test_backend_dockerfile_exists(self):
        """Verify backend Dockerfile exists"""
        dockerfile = REPO_ROOT / "backend" / "Dockerfile"
        assert dockerfile.exists(), "backend/Dockerfile not found"
    
    def test_frontend_dockerfile_exists(self):
        """Verify frontend Dockerfile exists"""
        dockerfile = REPO_ROOT / "frontend" / "Dockerfile"
        assert dockerfile.exists(), "frontend/Dockerfile not found"

    def test_self_hosted_dockerfile_removes_backend_env_files(self):
        """Verify self-hosted Dockerfile removes backend .env files.

        The self-hosted Dockerfile must remove backend/.env* files after copying
        backend sources to prevent development defaults (USE_MOCK_RESPONSES=true,
        DEBUG_MODE=true, ADMIN_USERNAME=admin, ADMIN_PASSWORD=admin123) from being
        baked into the production image.

        These defaults would cause startup validation failures in self-hosted
        production mode (ENVIRONMENT=production) even when no .env file is explicitly
        provided to the container.
        """
        dockerfile = REPO_ROOT / "Dockerfile.self-hosted"
        with open(dockerfile, 'r') as f:
            lines = f.readlines()

        # Find the line numbers for key operations
        copy_backend_line = None
        rm_env_backend_line = None

        for i, line in enumerate(lines):
            if 'COPY backend/' in line and copy_backend_line is None:
                copy_backend_line = i
            # Look for rm after we've seen COPY backend/
            if copy_backend_line is not None and rm_env_backend_line is None:
                if 'RUN rm -f .env' in line or ('rm -f .env' in line and i > copy_backend_line):
                    rm_env_backend_line = i

        assert copy_backend_line is not None, (
            "Dockerfile must copy backend sources with 'COPY backend/'"
        )

        assert rm_env_backend_line is not None, (
            "Dockerfile must remove .env files after copying backend sources with "
            "'rm -f .env' to prevent development defaults from being baked into the image"
        )

        assert rm_env_backend_line > copy_backend_line, (
            f"rm -f .env (line {rm_env_backend_line + 1}) must come after "
            f"COPY backend/ (line {copy_backend_line + 1}) to remove tracked .env files"
        )

    def test_backend_code_has_production_safe_defaults(self):
        """Verify backend code defaults to production-safe values.

        Even when no .env file or environment variables are set, the backend
        code must default to production-safe values to prevent self-hosted
        production containers from starting with development configurations.
        """
        import sys
        import importlib.util

        # Load auth.py module
        auth_path = REPO_ROOT / "backend" / "auth.py"
        spec = importlib.util.spec_from_file_location("auth_test", auth_path)
        auth_module = importlib.util.module_from_spec(spec)

        # Read the source to check default values
        with open(auth_path, 'r') as f:
            auth_source = f.read()

        # Check DEBUG_MODE default
        assert 'DEBUG_MODE = os.getenv("DEBUG_MODE", "false")' in auth_source, (
            "auth.py DEBUG_MODE must default to 'false' for production safety. "
            "Found in source but with wrong default value."
        )

        # Check USE_MOCK_RESPONSES default
        assert 'USE_MOCK_RESPONSES = os.getenv("USE_MOCK_RESPONSES", "false")' in auth_source, (
            "auth.py USE_MOCK_RESPONSES must default to 'false' for production safety"
        )

        # Check marketplace_webhooks.py as well
        webhooks_path = REPO_ROOT / "backend" / "marketplace_webhooks.py"
        with open(webhooks_path, 'r') as f:
            webhooks_source = f.read()

        assert 'DEBUG_MODE = os.getenv("DEBUG_MODE", "false")' in webhooks_source, (
            "marketplace_webhooks.py DEBUG_MODE must default to 'false' for production safety"
        )


class TestDeploymentDocumentation:
    """Test deployment documentation completeness"""
    
    def test_docker_deployment_modes_doc_exists(self):
        """Verify DOCKER_DEPLOYMENT_MODES.md exists"""
        doc = REPO_ROOT / "DOCKER_DEPLOYMENT_MODES.md"
        assert doc.exists(), "DOCKER_DEPLOYMENT_MODES.md not found"
    
    def test_installation_doc_exists(self):
        """Verify INSTALLATION.md exists"""
        doc = REPO_ROOT / "INSTALLATION.md"
        assert doc.exists(), "INSTALLATION.md not found"
    
    def test_license_key_guide_exists(self):
        """Verify LICENSE_KEY_GUIDE.md exists"""
        doc = REPO_ROOT / "LICENSE_KEY_GUIDE.md"
        assert doc.exists(), "LICENSE_KEY_GUIDE.md not found"
    
    def test_docker_deployment_doc_covers_both_modes(self):
        """Verify documentation covers both deployment modes"""
        doc = REPO_ROOT / "DOCKER_DEPLOYMENT_MODES.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'self-hosted' in content.lower()
        assert 'cloud' in content.lower()
    
    def test_docker_deployment_doc_has_troubleshooting(self):
        """Verify documentation includes troubleshooting"""
        doc = REPO_ROOT / "DOCKER_DEPLOYMENT_MODES.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'troubleshooting' in content.lower()
    
    def test_installation_doc_has_upgrade_instructions(self):
        """Verify installation doc has upgrade instructions"""
        doc = REPO_ROOT / "INSTALLATION.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'upgrade' in content.lower() or 'updating' in content.lower()
    
    def test_license_guide_explains_tiers(self):
        """Verify license guide explains all tiers"""
        doc = REPO_ROOT / "LICENSE_KEY_GUIDE.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'free' in content.lower()
        assert 'professional' in content.lower()
        assert 'enterprise' in content.lower()


class TestCommonErrorScenarios:
    """Test that common error scenarios are documented"""
    
    def test_expired_license_error_documented(self):
        """Verify expired license error is documented"""
        doc = REPO_ROOT / "LICENSE_KEY_GUIDE.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'expired' in content.lower()
    
    def test_invalid_license_error_documented(self):
        """Verify invalid license error is documented"""
        doc = REPO_ROOT / "LICENSE_KEY_GUIDE.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'invalid' in content.lower()
    
    def test_oauth_error_documented(self):
        """Verify OAuth errors are documented"""
        doc = REPO_ROOT / "DOCKER_DEPLOYMENT_MODES.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'oauth' in content.lower() or 'github' in content.lower()
    
    def test_port_conflict_error_documented(self):
        """Verify port conflict errors are documented"""
        # Check install script or docs for port conflict handling
        install_script = REPO_ROOT / "install.sh"
        with open(install_script, 'r') as f:
            content = f.read()
        
        assert 'port' in content.lower()


class TestUpgradeDowngradePaths:
    """Test upgrade and downgrade documentation"""
    
    def test_application_upgrade_documented(self):
        """Verify application upgrade process is documented"""
        doc = REPO_ROOT / "INSTALLATION.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'upgrade' in content.lower()
        assert 'docker' in content.lower()
    
    def test_license_tier_upgrade_documented(self):
        """Verify license tier upgrade is documented"""
        doc = REPO_ROOT / "INSTALLATION.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'tier' in content.lower() or 'license' in content.lower()
    
    def test_database_migration_documented(self):
        """Verify database migration process is documented"""
        doc = REPO_ROOT / "INSTALLATION.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'migration' in content.lower() or 'database' in content.lower()
    
    def test_mode_migration_documented(self):
        """Verify migration between modes is documented"""
        doc = REPO_ROOT / "DOCKER_DEPLOYMENT_MODES.md"
        with open(doc, 'r') as f:
            content = f.read()
        
        assert 'migration' in content.lower()


class TestReleaseWorkflowConfiguration:
    """Test self-hosted release workflow configuration."""

    def test_self_hosted_release_workflow_builds_multi_arch(self):
        """Verify self-hosted release workflow publishes amd64 and arm64 images."""
        workflow_file = REPO_ROOT / ".github" / "workflows" / "self-hosted-image.yml"
        with open(workflow_file, 'r') as f:
            content = f.read()

        assert 'docker/setup-qemu-action@v4' in content
        assert 'docker/setup-buildx-action@v3' in content
        assert 'platforms: linux/amd64,linux/arm64' in content

    def test_self_hosted_release_workflow_verifies_manifest_arches(self):
        """Verify workflow inspects published manifest for both required platforms."""
        workflow_file = REPO_ROOT / ".github" / "workflows" / "self-hosted-image.yml"
        with open(workflow_file, 'r') as f:
            content = f.read()

        assert 'docker buildx imagetools inspect' in content
        assert "grep -q 'linux/amd64'" in content
        assert "grep -q 'linux/arm64'" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
