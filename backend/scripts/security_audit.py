#!/usr/bin/env python3
"""
FilaOps Security Audit Script

Standalone script to verify security configuration post-deployment.
Can also be used programmatically by the admin dashboard API.

Usage:
  cd backend
  python scripts/security_audit.py
  python scripts/security_audit.py --json
  python scripts/security_audit.py --json --output report.json
"""
import sys
import os
import json
import math
import platform
import subprocess
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CheckStatus(str, Enum):
    """Status of a security check"""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    INFO = "info"


class CheckCategory(str, Enum):
    """Category/severity of a security check"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class CheckResult:
    """Result of a single security check"""
    id: str
    name: str
    category: CheckCategory
    status: CheckStatus
    message: str
    details: Optional[str] = None
    remediation: Optional[str] = None


# Known weak/default secret keys that should never be used
KNOWN_WEAK_SECRETS = [
    "change-this-to-a-random-secret-key-in-production",
    "your-secret-key-here",
    "secret",
    "changeme",
    "development-secret-key",
    "test-secret-key",
    "supersecretkey",
    "mysecretkey",
]


class SecurityAuditor:
    """
    Comprehensive security auditor for FilaOps installations.

    Runs a series of security checks and provides actionable remediation steps.
    Can be run as a CLI tool or imported by the API for dashboard display.
    """

    VERSION = "1.0"

    def __init__(self):
        self.results: List[CheckResult] = []
        self._settings = None
        self._load_settings()

    def _load_settings(self):
        """Load application settings"""
        try:
            from app.core.settings import get_settings
            self._settings = get_settings()
        except Exception:
            # Settings couldn't be loaded - we'll check for .env directly
            self._settings = None

    def run_all_checks(self) -> List[CheckResult]:
        """Run all security checks and return results"""
        self.results = []

        # Critical checks
        self._check_secret_key_not_default()
        self._check_secret_key_entropy()
        self._check_environment_production()
        self._check_debug_disabled()
        self._check_https_enabled()
        self._check_admin_password_changed()
        self._check_env_file_not_exposed()

        # Warning checks
        self._check_cors_not_wildcard()
        self._check_rate_limiting_enabled()
        self._check_database_ssl()
        self._check_dependencies_secure()
        self._check_backup_configured()

        # Informational checks
        self._check_external_ai_blocked()
        self._check_data_privacy_mode()

        return self.results

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of the audit"""
        passed = sum(1 for r in self.results if r.status == CheckStatus.PASS)
        failed = sum(1 for r in self.results if r.status == CheckStatus.FAIL)
        warnings = sum(1 for r in self.results if r.status == CheckStatus.WARN)
        info = sum(1 for r in self.results if r.status == CheckStatus.INFO)

        # Overall status: FAIL if any critical fails, WARN if any warnings, else PASS
        critical_fails = any(
            r.status == CheckStatus.FAIL and r.category == CheckCategory.CRITICAL
            for r in self.results
        )
        has_warnings = any(r.status == CheckStatus.WARN for r in self.results)

        if critical_fails:
            overall = "FAIL"
        elif has_warnings:
            overall = "WARN"
        else:
            overall = "PASS"

        return {
            "total_checks": len(self.results),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "info": info,
            "overall_status": overall
        }

    def get_system_info(self) -> Dict[str, Any]:
        """Get system information for the report"""
        info = {
            "os": f"{platform.system()} {platform.release()}",
            "python_version": platform.python_version(),
            "database": "Unknown",
            "reverse_proxy": "Unknown"
        }

        # Try to get database version
        try:
            from app.db.session import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            result = db.execute(text("SELECT version()")).scalar()
            if result:
                # Extract just the version part
                info["database"] = result.split(",")[0] if "," in result else result[:50]
            db.close()
        except Exception:
            pass

        # Check for Caddy
        try:
            result = subprocess.run(
                ["caddy", "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                info["reverse_proxy"] = f"Caddy {result.stdout.strip()}"
        except Exception:
            pass

        return info

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit results to dictionary for JSON export"""
        from app.core.version import VersionManager

        version_info = VersionManager.get_current_version()

        return {
            "audit_version": self.VERSION,
            "generated_at": datetime.now().isoformat(),
            "filaops_version": version_info.get("version", "unknown"),
            "environment": self._settings.ENVIRONMENT if self._settings else "unknown",
            "summary": self.get_summary(),
            "checks": [asdict(r) for r in self.results],
            "system_info": self.get_system_info()
        }

    # ==================
    # Critical Checks
    # ==================

    def _check_secret_key_not_default(self):
        """Check that SECRET_KEY is not a known default/weak value"""
        check_id = "secret_key_not_default"
        name = "SECRET_KEY Strength"
        category = CheckCategory.CRITICAL
        remediation = 'Generate a secure key: python -c "import secrets; print(secrets.token_urlsafe(64))"'

        if not self._settings:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.FAIL,
                message="Could not load settings to check SECRET_KEY",
                remediation="Ensure .env file exists and is readable"
            ))
            return

        secret = self._settings.SECRET_KEY

        # Check against known weak secrets
        if secret.lower() in [s.lower() for s in KNOWN_WEAK_SECRETS]:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.FAIL,
                message="Default/known weak SECRET_KEY detected!",
                remediation=remediation
            ))
            return

        # Check for common weak patterns
        weak_patterns = ["change", "default", "test", "example", "secret", "password"]
        if any(p in secret.lower() for p in weak_patterns):
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message="SECRET_KEY may contain weak patterns",
                remediation=remediation
            ))
            return

        self.results.append(CheckResult(
            id=check_id, name=name, category=category,
            status=CheckStatus.PASS,
            message="Strong key configured"
        ))

    def _check_secret_key_entropy(self):
        """Check that SECRET_KEY has sufficient entropy"""
        check_id = "secret_key_entropy"
        name = "SECRET_KEY Entropy"
        category = CheckCategory.CRITICAL
        remediation = "Generate a longer key with high entropy (at least 64 characters)"

        if not self._settings:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.FAIL,
                message="Could not load settings to check SECRET_KEY",
                remediation="Ensure .env file exists and is readable"
            ))
            return

        secret = self._settings.SECRET_KEY
        length = len(secret)

        # Calculate Shannon entropy
        entropy = self._calculate_entropy(secret)

        if length < 32:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.FAIL,
                message=f"SECRET_KEY too short ({length} chars, need 64+)",
                remediation=remediation
            ))
        elif length < 64:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message=f"SECRET_KEY could be longer ({length} chars)",
                remediation=remediation
            ))
        elif entropy < 3.5:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message=f"SECRET_KEY has low entropy ({entropy:.2f} bits/char)",
                remediation=remediation
            ))
        else:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message=f"{length} characters (good)"
            ))

    def _check_environment_production(self):
        """Check that ENVIRONMENT is set to production"""
        check_id = "environment_production"
        name = "Production Environment"
        category = CheckCategory.CRITICAL

        if not self._settings:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Could not load settings",
                remediation="Set ENVIRONMENT=production in .env"
            ))
            return

        env = self._settings.ENVIRONMENT.lower()

        if env == "production":
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message="ENVIRONMENT=production"
            ))
        elif env == "development":
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="ENVIRONMENT=development (expected for local dev)",
                details="Set to 'production' before deploying"
            ))
        else:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message=f"ENVIRONMENT={env} (should be 'production')",
                remediation="Set ENVIRONMENT=production in .env"
            ))

    def _check_debug_disabled(self):
        """Check that DEBUG mode is disabled"""
        check_id = "debug_disabled"
        name = "Debug Mode Disabled"
        category = CheckCategory.CRITICAL

        if not self._settings:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Could not load settings",
                remediation="Set DEBUG=false in .env"
            ))
            return

        if self._settings.DEBUG:
            # Check if we're in development
            if self._settings.ENVIRONMENT.lower() == "development":
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.INFO,
                    message="DEBUG=true (acceptable for development)",
                    details="Disable before deploying to production"
                ))
            else:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.FAIL,
                    message="DEBUG=true in non-development environment!",
                    remediation="Set DEBUG=false in .env"
                ))
        else:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message="DEBUG=false"
            ))

    def _check_https_enabled(self):
        """Check if application is served over HTTPS"""
        check_id = "https_enabled"
        name = "HTTPS Enabled"
        category = CheckCategory.CRITICAL

        # Check FRONTEND_URL for https
        https_configured = False
        https_origin_found = False

        if self._settings:
            frontend_url = self._settings.FRONTEND_URL or ""
            if frontend_url.startswith("https://"):
                https_configured = True

            # Also check if ALLOWED_ORIGINS contains any https URLs
            allowed_origins = getattr(self._settings, 'ALLOWED_ORIGINS', [])
            if allowed_origins:
                for origin in allowed_origins:
                    if origin.startswith("https://"):
                        https_origin_found = True
                        break

        # Check for localhost (development)
        if self._settings and self._settings.ENVIRONMENT.lower() == "development":
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Development mode - HTTPS not required",
                details="Configure TLS for production deployment"
            ))
            return

        # Check for Caddy (handles TLS automatically)
        caddy_found = False

        # First check if Caddyfile exists (means Caddy is configured)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        caddyfile_path = os.path.join(project_root, "Caddyfile")
        caddyfile_exists = os.path.exists(caddyfile_path)

        # Check for caddy executable
        try:
            # Try system caddy first
            result = subprocess.run(
                ["caddy", "version"],
                capture_output=True,
                timeout=5
            )
            caddy_found = result.returncode == 0
        except Exception:
            pass

        # On Windows, also check for local caddy.exe
        if not caddy_found and platform.system() == "Windows":
            local_caddy = os.path.join(project_root, "caddy.exe")
            if os.path.exists(local_caddy):
                caddy_found = True

        if https_configured:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message="HTTPS URLs configured"
            ))
        elif caddy_found and caddyfile_exists:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message="TLS available via Caddy",
                details="Caddyfile configured and Caddy installed"
            ))
        elif caddyfile_exists and https_origin_found:
            # Caddyfile exists and CORS has https origin - likely configured
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message="HTTPS configured via Caddy",
                details="Caddyfile found with HTTPS origins in CORS"
            ))
        elif caddy_found:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message="TLS available via Caddy"
            ))
        else:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message="HTTPS not detected",
                remediation="Configure Caddy or another reverse proxy with TLS"
            ))

    def _check_admin_password_changed(self):
        """Check that default admin password has been changed"""
        check_id = "admin_password_changed"
        name = "Admin Password Changed"
        category = CheckCategory.CRITICAL

        try:
            from app.db.session import SessionLocal
            from app.models import User
            from app.core.security import verify_password

            db = SessionLocal()
            # Find users with admin account_type
            admin_users = db.query(User).filter(User.account_type == "admin").all()

            if not admin_users:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.INFO,
                    message="No admin users found",
                    details="Admin users may not exist yet"
                ))
                db.close()
                return

            # Check against common default passwords
            default_passwords = ["admin", "Admin", "password", "Password123", "admin123", "changeme"]

            for admin_user in admin_users:
                for pwd in default_passwords:
                    try:
                        if verify_password(pwd, admin_user.password_hash):
                            self.results.append(CheckResult(
                                id=check_id, name=name, category=category,
                                status=CheckStatus.FAIL,
                                message=f"Admin '{admin_user.email}' uses a default password!",
                                remediation="Change admin password via Settings > Users"
                            ))
                            db.close()
                            return
                    except Exception:
                        # Password hash may be in different format
                        pass

            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message="Admin passwords have been changed"
            ))
            db.close()

        except Exception as e:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message=f"Could not verify admin password: {str(e)[:50]}",
                remediation="Manually verify admin password has been changed"
            ))

    def _check_env_file_not_exposed(self):
        """Check that .env file is not web-accessible"""
        check_id = "env_file_not_exposed"
        name = ".env Not Accessible"
        category = CheckCategory.CRITICAL

        # In development, this is less critical
        if self._settings and self._settings.ENVIRONMENT.lower() == "development":
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Development mode - .env protection not critical",
                details="Ensure reverse proxy blocks dotfiles in production"
            ))
            return

        # Find a production URL to test - prefer HTTPS origins over FRONTEND_URL
        test_url = None
        allowed_origins = getattr(self._settings, 'ALLOWED_ORIGINS', []) if self._settings else []

        # First, look for HTTPS origins in ALLOWED_ORIGINS
        for origin in allowed_origins:
            if origin.startswith("https://"):
                test_url = origin
                break

        # Fall back to FRONTEND_URL if no HTTPS origin found
        if not test_url:
            frontend_url = self._settings.FRONTEND_URL if self._settings else ""
            is_localhost = any(
                h in frontend_url.lower()
                for h in ["localhost", "127.0.0.1", "0.0.0.0"]
            )
            if not is_localhost:
                test_url = frontend_url

        # If we only have localhost URLs, skip the check
        if not test_url:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Localhost detected - .env check skipped",
                details="This check runs on real production URLs only"
            ))
            return

        # Try to access .env via the production URL
        try:
            import requests

            url = f"{test_url}/.env"
            try:
                # Use verify=False for self-signed certs (like Caddy's local TLS)
                response = requests.get(url, timeout=5, allow_redirects=False, verify=False)
                if response.status_code == 200:
                    self.results.append(CheckResult(
                        id=check_id, name=name, category=category,
                        status=CheckStatus.FAIL,
                        message=".env file is web-accessible!",
                        remediation="Configure reverse proxy to block dotfiles"
                    ))
                    return
                else:
                    self.results.append(CheckResult(
                        id=check_id, name=name, category=category,
                        status=CheckStatus.PASS,
                        message=f".env blocked (HTTP {response.status_code})",
                        details=f"Tested via {test_url}"
                    ))
                    return
            except requests.exceptions.RequestException as e:
                # Can't reach URL - might be offline or blocked
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.INFO,
                    message="Could not test .env exposure",
                    details=f"URL {test_url} not reachable: {str(e)[:50]}"
                ))
                return

        except ImportError:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Could not test .env exposure (requests not installed)",
                remediation="Manually verify .env is blocked by reverse proxy"
            ))

    # ==================
    # Warning Checks
    # ==================

    def _check_cors_not_wildcard(self):
        """Check that CORS doesn't allow wildcard origins"""
        check_id = "cors_not_wildcard"
        name = "CORS Configuration"
        category = CheckCategory.WARNING

        if not self._settings:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Could not load settings"
            ))
            return

        origins = self._settings.ALLOWED_ORIGINS

        # Check for different origin types
        has_localhost = any("localhost" in o or "127.0.0.1" in o for o in origins)
        has_https = any(o.startswith("https://") for o in origins)

        if "*" in origins:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message="Wildcard (*) origin detected",
                remediation="Set specific origins in ALLOWED_ORIGINS"
            ))
        elif has_localhost:
            if self._settings.ENVIRONMENT.lower() == "development":
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.PASS,
                    message="Localhost origins configured (OK for development)"
                ))
            elif has_https:
                # Hybrid setup: localhost for dev + HTTPS for production access
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.PASS,
                    message="Hybrid setup: localhost + HTTPS origins",
                    details="Localhost for development, HTTPS for production access"
                ))
            else:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.WARN,
                    message="Localhost origins in non-development environment",
                    remediation="Remove localhost origins for production"
                ))
        else:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message=f"{len(origins)} specific origins configured"
            ))

    def _check_rate_limiting_enabled(self):
        """Check if rate limiting is enabled"""
        check_id = "rate_limiting_enabled"
        name = "Rate Limiting"
        category = CheckCategory.WARNING

        try:
            from app.core.limiter import HAS_SLOWAPI

            if HAS_SLOWAPI:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.PASS,
                    message="SlowAPI rate limiting available"
                ))
            else:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.WARN,
                    message="Rate limiting not installed",
                    remediation="Install slowapi: pip install slowapi"
                ))
        except ImportError:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message="Could not check rate limiting status",
                remediation="Verify rate_limit.py middleware is active"
            ))

    def _check_database_ssl(self):
        """Check if database connection uses SSL"""
        check_id = "database_ssl"
        name = "Database SSL"
        category = CheckCategory.WARNING

        if not self._settings:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Could not load settings"
            ))
            return

        db_url = self._settings.database_url

        # Check for SSL in connection string
        if "sslmode=require" in db_url or "sslmode=verify" in db_url:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message="SSL enabled for database connection"
            ))
        elif "localhost" in db_url or "127.0.0.1" in db_url:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Local database - SSL not required"
            ))
        else:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message="Database SSL not detected",
                remediation="Add ?sslmode=require to DATABASE_URL"
            ))

    def _check_dependencies_secure(self):
        """Check for known vulnerabilities in dependencies"""
        check_id = "dependencies_secure"
        name = "Dependencies Secure"
        category = CheckCategory.WARNING

        try:
            # Try pip-audit first
            result = subprocess.run(
                [sys.executable, "-m", "pip_audit", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=120
            )

            # pip-audit returns exit code 1 when vulnerabilities are found (not just 0)
            # So we check if we got valid JSON output instead of relying on return code
            if result.stdout and result.stdout.strip().startswith("{"):
                try:
                    audit_data = json.loads(result.stdout)
                    # pip-audit format: {"dependencies": [{"name": "pkg", "vulns": [...]}], "fixes": []}
                    vulnerable_packages = []
                    for dep in audit_data.get("dependencies", []):
                        if dep.get("vulns") and len(dep.get("vulns", [])) > 0:
                            vulnerable_packages.append(dep.get("name"))

                    if vulnerable_packages:
                        vuln_count = len(vulnerable_packages)
                        self.results.append(CheckResult(
                            id=check_id, name=name, category=category,
                            status=CheckStatus.WARN,
                            message=f"{vuln_count} packages have known CVEs",
                            remediation="Run: pip install pip-audit && pip-audit --fix"
                        ))
                    else:
                        self.results.append(CheckResult(
                            id=check_id, name=name, category=category,
                            status=CheckStatus.PASS,
                            message="No known vulnerabilities found"
                        ))
                except json.JSONDecodeError:
                    # JSON parsing failed, pip-audit might not be working properly
                    self.results.append(CheckResult(
                        id=check_id, name=name, category=category,
                        status=CheckStatus.INFO,
                        message="pip-audit output error",
                        remediation="Run: pip install pip-audit && pip-audit"
                    ))
            else:
                # No valid JSON output - pip-audit probably not installed
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.INFO,
                    message="pip-audit not installed",
                    remediation="Run: pip install pip-audit && pip-audit"
                ))

        except subprocess.TimeoutExpired:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="Dependency check timed out"
            ))
        except Exception as e:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message=f"Could not check dependencies: {str(e)[:50]}",
                remediation="Run: pip install pip-audit && pip-audit"
            ))

    def _check_backup_configured(self):
        """Check if database backup is configured"""
        check_id = "backup_configured"
        name = "Backup Configured"
        category = CheckCategory.WARNING

        # Check for common backup indicators
        backup_indicators = []

        # Check for pg_dump in scheduled tasks (Windows)
        try:
            result = subprocess.run(
                ["schtasks", "/query", "/fo", "csv"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if "pg_dump" in result.stdout.lower() or "backup" in result.stdout.lower():
                backup_indicators.append("Windows scheduled task")
        except Exception:
            pass

        # Check for backup script files
        backup_paths = [
            Path("./backup.sh"),
            Path("./scripts/backup.sh"),
            Path("../backup.sh"),
            Path("/etc/cron.d/filaops-backup"),
        ]

        for path in backup_paths:
            if path.exists():
                backup_indicators.append(f"Backup script: {path}")

        if backup_indicators:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.PASS,
                message=f"Backup detected: {backup_indicators[0]}"
            ))
        else:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.WARN,
                message="No backup configuration detected",
                remediation="Set up pg_dump cron job or backup service"
            ))

    # ==================
    # Informational Checks
    # ==================

    def _check_external_ai_blocked(self):
        """Check if external AI services are blocked for data privacy"""
        check_id = "external_ai_blocked"
        name = "External AI Blocked (Optional)"
        category = CheckCategory.INFO

        try:
            from app.db.session import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()

            # Check company_settings for external_ai_blocked
            result = db.execute(
                text("SELECT external_ai_blocked FROM company_settings LIMIT 1")
            ).scalar()

            db.close()

            if result is True:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.PASS,
                    message="External AI services blocked"
                ))
            else:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.INFO,
                    message="External AI services allowed",
                    details="Enable in Settings > AI Configuration if data privacy required"
                ))

        except Exception:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="AI configuration not found",
                details="Configure AI settings in admin dashboard"
            ))

    def _check_data_privacy_mode(self):
        """Check AI provider configuration for data privacy"""
        check_id = "data_privacy_mode"
        name = "Data Privacy Mode"
        category = CheckCategory.INFO

        try:
            from app.db.session import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()

            result = db.execute(
                text("SELECT ai_provider FROM company_settings LIMIT 1")
            ).scalar()

            db.close()

            if result and result.lower() == "ollama":
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.PASS,
                    message="Ollama (local) configured - data stays on-premise"
                ))
            elif result:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.INFO,
                    message=f"AI Provider: {result}",
                    details="Data may be sent to external services"
                ))
            else:
                self.results.append(CheckResult(
                    id=check_id, name=name, category=category,
                    status=CheckStatus.INFO,
                    message="No AI provider configured"
                ))

        except Exception:
            self.results.append(CheckResult(
                id=check_id, name=name, category=category,
                status=CheckStatus.INFO,
                message="AI provider configuration not available"
            ))

    # ==================
    # Utility Methods
    # ==================

    @staticmethod
    def _calculate_entropy(text: str) -> float:
        """Calculate Shannon entropy of a string"""
        if not text:
            return 0.0

        # Count character frequencies
        freq = {}
        for char in text:
            freq[char] = freq.get(char, 0) + 1

        # Calculate entropy
        length = len(text)
        entropy = 0.0
        for count in freq.values():
            p = count / length
            entropy -= p * math.log2(p)

        return entropy


def print_console_report(auditor: SecurityAuditor):
    """Print formatted console output"""
    summary = auditor.get_summary()
    results = auditor.results

    # Group results by category
    critical = [r for r in results if r.category == CheckCategory.CRITICAL]
    warnings = [r for r in results if r.category == CheckCategory.WARNING]
    info = [r for r in results if r.category == CheckCategory.INFO]

    # Status icons - use ASCII fallbacks for Windows compatibility
    try:
        # Test if we can print unicode
        "\u2705".encode(sys.stdout.encoding or 'utf-8')
        icons = {
            CheckStatus.PASS: "\u2705",  # Green check
            CheckStatus.FAIL: "\u274c",  # Red X
            CheckStatus.WARN: "\u26a0\ufe0f",  # Warning
            CheckStatus.INFO: "\u2139\ufe0f",  # Info
        }
    except (UnicodeEncodeError, LookupError):
        # ASCII fallback for Windows
        icons = {
            CheckStatus.PASS: "[OK]",
            CheckStatus.FAIL: "[X]",
            CheckStatus.WARN: "[!]",
            CheckStatus.INFO: "[i]",
        }

    # Header
    print()
    print("=" * 72)
    print(f"                    FilaOps Security Audit v{SecurityAuditor.VERSION}")
    print(f"                    Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    # Critical checks
    print()
    print("  CRITICAL CHECKS")
    print("  " + "-" * 15)
    for r in critical:
        icon = icons.get(r.status, "?")
        print(f"  {icon} {r.name:<30} {r.message}")

    # Warning checks
    print()
    print("  WARNINGS")
    print("  " + "-" * 8)
    for r in warnings:
        icon = icons.get(r.status, "?")
        print(f"  {icon} {r.name:<30} {r.message}")

    # Informational checks
    print()
    print("  INFORMATIONAL")
    print("  " + "-" * 13)
    for r in info:
        icon = icons.get(r.status, "?")
        print(f"  {icon} {r.name:<30} {r.message}")

    # Summary
    print()
    print("=" * 72)
    if summary["overall_status"] == "PASS":
        status_icon = icons[CheckStatus.PASS]
    elif summary["overall_status"] == "WARN":
        status_icon = icons[CheckStatus.WARN]
    else:
        status_icon = icons[CheckStatus.FAIL]
    print(f"  SUMMARY: {summary['passed']} PASS | {summary['warnings']} WARN | {summary['failed']} FAIL")
    print()

    if summary["overall_status"] == "FAIL":
        print(f"  {status_icon} ACTION REQUIRED: Critical issues must be resolved")
    elif summary["overall_status"] == "WARN":
        print(f"  {status_icon} ATTENTION: Warnings should be reviewed")
    else:
        print(f"  {status_icon} ALL CLEAR: No critical security issues detected")

    print("=" * 72)

    # Failed checks remediation
    failed = [r for r in results if r.status == CheckStatus.FAIL]
    if failed:
        print()
        print("FAILED CHECKS - REMEDIATION REQUIRED:")
        print("-" * 38)
        for i, r in enumerate(failed, 1):
            print(f"\n{i}. {r.name} [CRITICAL]")
            print(f"   Issue: {r.message}")
            if r.remediation:
                print(f"   Fix: {r.remediation}")

    # Warnings remediation
    warned = [r for r in results if r.status == CheckStatus.WARN]
    if warned:
        print()
        print("WARNINGS - RECOMMENDED FIXES:")
        print("-" * 28)
        for i, r in enumerate(warned, 1):
            print(f"\n{i}. {r.name}")
            print(f"   Issue: {r.message}")
            if r.remediation:
                print(f"   Fix: {r.remediation}")

    print()


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="FilaOps Security Audit Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/security_audit.py           # Console output
  python scripts/security_audit.py --json    # JSON to stdout
  python scripts/security_audit.py --json --output report.json
        """
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Write output to file"
    )

    args = parser.parse_args()

    # Run audit
    auditor = SecurityAuditor()
    auditor.run_all_checks()

    if args.json:
        output = json.dumps(auditor.to_dict(), indent=2, default=str)

        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Report written to {args.output}")
        else:
            print(output)
    else:
        print_console_report(auditor)

        if args.output:
            # Also write JSON to file if output specified
            with open(args.output, "w") as f:
                json.dump(auditor.to_dict(), f, indent=2, default=str)
            print(f"\nJSON report also written to {args.output}")

    # Exit with appropriate code
    summary = auditor.get_summary()
    if summary["overall_status"] == "FAIL":
        sys.exit(1)
    elif summary["overall_status"] == "WARN":
        sys.exit(0)  # Warnings don't fail CI
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
