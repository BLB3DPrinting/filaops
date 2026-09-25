"""
Security Audit API Endpoints

Provides security audit functionality for the admin dashboard:
- Run security audits
- Export audit reports
- Check security status
"""
import re
import sys
import os
from datetime import datetime
from typing import List, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user
from app.core.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/security", tags=["Security"])


def require_local_remediation():
    """Dependency that blocks remediation endpoints in production.

    Reads ENVIRONMENT the same way as the startup production checks in
    settings.py (trimmed, any case), so "production " or "Production" also
    block. It is only an environment check: a Docker install keeps the
    default ENVIRONMENT=development, so these routes stay open to admins there.
    """
    environment = str(getattr(settings, "ENVIRONMENT", "development") or "")
    if environment.strip().lower() == "production":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is disabled in production environments"
        )


def validate_domain(domain: str) -> str:
    """Validate domain against strict pattern to prevent injection."""
    domain = domain.strip().lower()
    if not domain:
        raise HTTPException(status_code=400, detail="Domain cannot be empty")
    if len(domain) > 253:
        raise HTTPException(status_code=400, detail="Domain too long")
    # Strict domain pattern: letters, numbers, dots, hyphens only
    pattern = r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$'
    if not re.match(pattern, domain):
        raise HTTPException(status_code=400, detail="Invalid domain format")
    # Reject any shell metacharacters as extra safety
    dangerous_chars = ['"', "'", ';', '&', '|', '$', '`', '(', ')', '{', '}', '<', '>', '\\', '\n', '\r']
    if any(char in domain for char in dangerous_chars):
        raise HTTPException(status_code=400, detail="Domain contains invalid characters")
    return domain


# ============================================================================
# SCHEMAS
# ============================================================================

class CheckStatusEnum(str, Enum):
    """Status of a security check"""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    INFO = "info"


class CheckCategoryEnum(str, Enum):
    """Category/severity of a security check"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class SecurityCheck(BaseModel):
    """Single security check result"""
    id: str
    name: str
    category: str
    status: str
    message: str
    details: Optional[str] = None
    remediation: Optional[str] = None


class SecuritySummary(BaseModel):
    """Summary of security audit"""
    total_checks: int
    passed: int
    failed: int
    warnings: int
    info: int
    overall_status: str  # PASS, WARN, or FAIL


class SystemInfo(BaseModel):
    """System information"""
    os: str
    python_version: str
    database: str
    reverse_proxy: str


class SecurityAuditResponse(BaseModel):
    """Full security audit response"""
    audit_version: str
    generated_at: str
    filaops_version: str
    environment: str
    summary: SecuritySummary
    checks: List[SecurityCheck]
    system_info: SystemInfo


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def run_security_audit() -> dict:
    """Run the security audit and return results as dict"""
    # Add scripts directory to path if needed
    scripts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "scripts"
    )
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    try:
        from scripts.security_audit import SecurityAuditor

        auditor = SecurityAuditor()
        auditor.run_all_checks()
        return auditor.to_dict()
    except ImportError as e:
        logger.error(f"Failed to import security_audit module: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Security audit module not found: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Security audit failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Security audit failed: {str(e)}"
        )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/audit", response_model=SecurityAuditResponse)
async def get_security_audit(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run security audit and return results.

    Requires admin authentication.
    """
    # Require admin role
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    logger.info(f"Security audit requested by {current_user.email}")

    result = run_security_audit()

    # Convert to response model
    return SecurityAuditResponse(
        audit_version=result.get("audit_version", "1.0"),
        generated_at=result.get("generated_at", datetime.now().isoformat()),
        filaops_version=result.get("filaops_version", "unknown"),
        environment=result.get("environment", "unknown"),
        summary=SecuritySummary(**result.get("summary", {
            "total_checks": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "info": 0,
            "overall_status": "UNKNOWN"
        })),
        checks=[SecurityCheck(**check) for check in result.get("checks", [])],
        system_info=SystemInfo(**result.get("system_info", {
            "os": "unknown",
            "python_version": "unknown",
            "database": "unknown",
            "reverse_proxy": "unknown"
        }))
    )


@router.get("/audit/export")
async def export_security_audit(
    format: str = "json",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Export security audit report.

    Formats: json (default)
    Future: pdf

    Requires admin authentication.
    """
    # Require admin role
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    if format not in ["json"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported format. Available: json"
        )

    logger.info(f"Security audit export ({format}) requested by {current_user.email}")

    result = run_security_audit()

    if format == "json":
        # Add export metadata
        result["exported_at"] = datetime.now().isoformat()
        result["exported_by"] = current_user.email

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"filaops_security_audit_{timestamp}.json"
        return JSONResponse(
            content=result,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    # Future: PDF export
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="PDF export not yet implemented"
    )


@router.get("/status")
async def get_security_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get quick security status overview.

    Returns a simplified status for display in navigation/header.
    Requires authentication.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    try:
        result = run_security_audit()
        summary = result.get("summary", {})

        overall = summary.get("overall_status", "UNKNOWN")
        critical_fails = summary.get("failed", 0)
        warnings = summary.get("warnings", 0)

        # Determine status level for UI
        if overall == "FAIL":
            status_level = "critical"
            status_message = f"{critical_fails} critical issue(s) require attention"
        elif overall == "WARN":
            status_level = "warning"
            status_message = f"{warnings} warning(s) should be reviewed"
        elif overall == "PASS":
            status_level = "healthy"
            status_message = "All security checks passed"
        else:
            status_level = "unknown"
            status_message = "Security status unknown"

        return {
            "status": status_level,
            "message": status_message,
            "summary": summary,
            "checked_at": result.get("generated_at", datetime.now().isoformat())
        }

    except Exception as e:
        logger.error(f"Failed to get security status: {e}")
        return {
            "status": "error",
            "message": "Could not check security status. Check server logs for details.",
            "summary": None,
            "checked_at": datetime.now().isoformat()
        }


# ============================================================================
# REMEDIATION HELPERS
# ============================================================================

@router.post("/remediate/generate-secret-key")
async def generate_secret_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Generate a secure SECRET_KEY for the user to copy.

    Does NOT automatically update the .env file - user must do that manually.
    This is intentional for security (we don't want to auto-modify config files).
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    import secrets
    new_key = secrets.token_urlsafe(64)

    logger.info(f"SECRET_KEY generated for remediation by {current_user.email}")

    return {
        "secret_key": new_key,
        "length": len(new_key),
        "instructions": [
            "Copy the generated key above",
            "Open your backend/.env file",
            "Find the line: SECRET_KEY=...",
            "Replace the value with the new key",
            "Save the file and restart the backend"
        ]
    }


@router.post("/remediate/open-env-file")
async def open_env_file(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Open the .env file in the system's default text editor.

    Makes it easy for non-technical users to edit configuration.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    # Find the .env file path (backend/.env, same as settings.py)
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )))
    env_path = os.path.join(backend_dir, ".env")

    if not os.path.exists(env_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration file not found at {env_path}"
        )

    # SEC-401: Do not spawn OS GUI processes (notepad/open/xdg-open) from backend API.
    # Return safe path and remediation instructions for manual or terminal editing.
    logger.info(f"Env file path requested by {current_user.email}")
    return {
        "success": True,
        "env_path": env_path,
        "message": f"Configuration file located at {env_path}. Edit this file using your preferred editor.",
    }


@router.post("/remediate/update-secret-key")
async def update_secret_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Automatically update the SECRET_KEY in the .env file.

    This is the easy mode for non-technical users.
    Generates a new key and updates the file automatically.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    import secrets
    import re

    # Find the .env file path (backend/.env, same as settings.py)
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )))
    env_path = os.path.join(backend_dir, ".env")

    # Generate new key
    new_key = secrets.token_urlsafe(64)

    if not os.path.exists(env_path):
        # Docker or env-var-only deployment — no .env file to write to.
        # Return the generated key for the user to copy manually.
        logger.info(
            f"SECRET_KEY generated (manual mode) by {current_user.email} — "
            f".env not found at {env_path}"
        )
        return {
            "success": True,
            "manual": True,
            "message": (
                "No .env file found — you're likely running in Docker. "
                "Copy the key below and add it to your host .env or "
                "docker-compose.yml, then restart the backend."
            ),
            "new_key": new_key,
            "requires_restart": True,
        }

    try:
        # Read current .env content
        with open(env_path, "r") as f:
            content = f.read()

        # Replace SECRET_KEY line
        pattern = r'^SECRET_KEY=.*$'
        new_line = f'SECRET_KEY={new_key}'

        if re.search(pattern, content, re.MULTILINE):
            new_content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
        else:
            # If SECRET_KEY doesn't exist, add it
            new_content = content + f"\nSECRET_KEY={new_key}\n"

        # Write back
        with open(env_path, "w") as f:
            f.write(new_content)

        logger.info(f"SECRET_KEY auto-updated by {current_user.email}")

        return {
            "success": True,
            "manual": False,
            "message": "SECRET_KEY has been updated! Please restart the backend.",
            "new_key_preview": f"{new_key[:20]}...",
            "requires_restart": True,
        }

    except Exception as e:
        logger.error(f"Failed to update SECRET_KEY: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update configuration: {str(e)}"
        )


@router.post("/remediate/open-restart-terminal")
async def open_restart_terminal(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Open a terminal window with instructions to restart the backend.

    Makes it easy for non-technical users who may not have a terminal open.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    # Find the project root
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )))
    project_root = os.path.dirname(backend_dir)
    restart_cmd = ".\\start-backend.ps1" if sys.platform == "win32" else "./start-backend.sh"

    # SEC-401: Do not spawn OS terminal windows from backend API.
    logger.info(f"Restart instructions requested by {current_user.email}")
    return {
        "success": True,
        "project_root": project_root,
        "restart_command": restart_cmd,
        "message": f"To restart the backend, navigate to {project_root} and run: {restart_cmd}",
    }


@router.post("/remediate/fix-dependencies")
async def fix_dependencies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Automatically scan and fix vulnerable dependencies.

    This uses pip-audit to identify and upgrade vulnerable packages.
    Non-technical users don't need to know about venvs or pip.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    import subprocess

    # Find the venv path (backend/venv)
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )))

    # Determine pip and python paths based on OS
    import platform
    if platform.system() == "Windows":
        pip_path = os.path.join(backend_dir, "venv", "Scripts", "pip.exe")
        python_path = os.path.join(backend_dir, "venv", "Scripts", "python.exe")
    else:
        pip_path = os.path.join(backend_dir, "venv", "bin", "pip")
        python_path = os.path.join(backend_dir, "venv", "bin", "python")

    if not os.path.exists(pip_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Virtual environment not found at {os.path.dirname(pip_path)}"
        )

    results = {
        "pip_audit_installed": False,
        "vulnerabilities_found": 0,
        "packages_upgraded": [],
        "errors": [],
        "requires_restart": False
    }

    try:
        # Step 1: Ensure pip-audit is installed
        logger.info("Checking pip-audit installation...")
        check_audit = subprocess.run(
            [python_path, "-m", "pip_audit", "--version"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if check_audit.returncode != 0:
            # Install pip-audit
            logger.info("Installing pip-audit...")
            install_result = subprocess.run(
                [pip_path, "install", "pip-audit"],
                capture_output=True,
                text=True,
                timeout=120
            )
            if install_result.returncode != 0:
                results["errors"].append(f"Failed to install pip-audit: {install_result.stderr}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not install pip-audit"
                )

        results["pip_audit_installed"] = True

        # Step 2: Run pip-audit to check for vulnerabilities
        logger.info("Running pip-audit scan...")
        audit_result = subprocess.run(
            [python_path, "-m", "pip_audit", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120
        )

        vulnerable_packages = []
        if audit_result.stdout:
            try:
                import json
                audit_data = json.loads(audit_result.stdout)
                # pip-audit format: {"dependencies": [{"name": "pkg", "vulns": [...]}], "fixes": []}
                dependencies = audit_data.get("dependencies", [])
                for dep in dependencies:
                    if dep.get("vulns") and len(dep.get("vulns", [])) > 0:
                        vulnerable_packages.append(dep.get("name"))
                results["vulnerabilities_found"] = len(vulnerable_packages)
            except json.JSONDecodeError:
                # pip-audit might output non-JSON if no vulnerabilities
                pass

        if not vulnerable_packages:
            logger.info("No vulnerabilities found!")
            return {
                "success": True,
                "message": "No known vulnerabilities found in your dependencies!",
                **results
            }

        # Step 3: Upgrade vulnerable packages
        logger.info(f"Found {len(vulnerable_packages)} vulnerable packages, upgrading...")
        packages_to_upgrade = list(set(vulnerable_packages))

        for package in packages_to_upgrade:
            logger.info(f"Upgrading {package}...")
            # Use python -m pip for pip self-upgrades (pip can't upgrade itself directly)
            if package.lower() == "pip":
                upgrade_result = subprocess.run(
                    [python_path, "-m", "pip", "install", "--upgrade", "pip"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            else:
                upgrade_result = subprocess.run(
                    [pip_path, "install", "--upgrade", package],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            if upgrade_result.returncode == 0:
                results["packages_upgraded"].append(package)
            else:
                results["errors"].append(f"Failed to upgrade {package}: {upgrade_result.stderr[:200]}")

        results["requires_restart"] = len(results["packages_upgraded"]) > 0

        logger.info(f"Dependencies fixed by {current_user.email}")

        if results["packages_upgraded"]:
            return {
                "success": True,
                "message": f"Upgraded {len(results['packages_upgraded'])} package(s). Please restart the backend.",
                **results
            }
        else:
            return {
                "success": False,
                "message": "Could not upgrade vulnerable packages. See errors for details.",
                **results
            }

    except subprocess.TimeoutExpired:
        logger.error("Dependency fix timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Operation timed out. Try running pip-audit manually."
        )
    except Exception as e:
        logger.error(f"Failed to fix dependencies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not fix dependencies: {str(e)}"
        )


@router.post("/remediate/fix-rate-limiting")
async def fix_rate_limiting(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Automatically install slowapi for rate limiting.

    FilaOps auto-detects slowapi on startup and enables rate limiting.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    import subprocess

    # Find the venv pip path
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )))

    import platform
    if platform.system() == "Windows":
        pip_path = os.path.join(backend_dir, "venv", "Scripts", "pip.exe")
    else:
        pip_path = os.path.join(backend_dir, "venv", "bin", "pip")

    if not os.path.exists(pip_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Virtual environment not found at {os.path.dirname(pip_path)}"
        )

    try:
        logger.info("Installing slowapi for rate limiting...")
        result = subprocess.run(
            [pip_path, "install", "slowapi"],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            logger.info(f"Rate limiting installed by {current_user.email}")
            return {
                "success": True,
                "message": "SlowAPI installed! Restart the backend to enable rate limiting.",
                "requires_restart": True
            }
        else:
            logger.error(f"Failed to install slowapi: {result.stderr}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Installation failed: {result.stderr[:200]}"
            )

    except subprocess.TimeoutExpired:
        logger.error("Rate limiting installation timed out")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Installation timed out. Try running: pip install slowapi"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install rate limiting: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not install rate limiting: {str(e)}"
        )


class SetupHTTPSRequest(BaseModel):
    """Request body for HTTPS setup"""
    domain: str


@router.post("/remediate/setup-https")
async def setup_https(
    request: SetupHTTPSRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Safely configure HTTPS with Caddy reverse proxy.

    Generates Caddyfile and updates Vite configuration without executing
    arbitrary shell scripts or downloading remote binaries (SEC-401).
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    import shutil

    domain = validate_domain(request.domain)

    # Find the project root
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )))
    project_root = os.path.dirname(backend_dir)

    caddy_installed = shutil.which("caddy") is not None or os.path.exists(os.path.join(project_root, "caddy.exe"))

    results = {
        "caddy_installed": caddy_installed,
        "caddy_was_installed": False,
        "caddyfile_created": False,
        "caddy_started": False,
        "domain": domain,
        "errors": []
    }

    # Step 1: Create Caddyfile
    logger.info(f"Creating Caddyfile for domain: {domain}")
    caddyfile_path = os.path.join(project_root, "Caddyfile")

    caddyfile_content = f"""{domain} {{
    # API requests go to the backend (port 8000)
    @api path /api/* /docs /openapi.json /health
    reverse_proxy @api localhost:8000

    # Everything else goes to the frontend (port 5173)
    reverse_proxy localhost:5173

    # Security: Block sensitive files
    @blocked path /.env /.git/* /.*
    respond @blocked 404

    # Enable compression
    encode gzip

    # Logging
    log {{
        output file access.log
    }}
}}
"""

    try:
        with open(caddyfile_path, "w") as f:
            f.write(caddyfile_content)
        results["caddyfile_created"] = True
        logger.info(f"Caddyfile created at {caddyfile_path}")
    except Exception as e:
        results["errors"].append(f"Failed to create Caddyfile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create Caddyfile: {str(e)}"
        )

    # Step 2: Update vite.config.js to allow the domain
    vite_config_path = os.path.join(project_root, "frontend", "vite.config.js")
    if os.path.exists(vite_config_path):
        try:
            with open(vite_config_path, "r") as f:
                vite_content = f.read()

            if "allowedHosts" not in vite_content:
                vite_content = vite_content.replace(
                    "export default defineConfig({",
                    f"""export default defineConfig({{
  server: {{
    allowedHosts: ['localhost', '{domain}'],
  }},"""
                )
                with open(vite_config_path, "w") as f:
                    f.write(vite_content)
                logger.info(f"Updated vite.config.js with allowedHosts for {domain}")
                results["vite_updated"] = True
            elif domain not in vite_content:
                import re
                pattern = r"allowedHosts:\s*\[([^\]]*)\]"
                match = re.search(pattern, vite_content)
                if match:
                    current_hosts = match.group(1)
                    new_hosts = f"{current_hosts}, '{domain}'"
                    vite_content = re.sub(pattern, f"allowedHosts: [{new_hosts}]", vite_content)
                    with open(vite_config_path, "w") as f:
                        f.write(vite_content)
                    logger.info(f"Added {domain} to vite.config.js allowedHosts")
                    results["vite_updated"] = True
        except Exception as e:
            logger.warning(f"Could not update vite.config.js: {e}")
            results["errors"].append(f"Could not update Vite config: {str(e)}")

    # SEC-401: Do not execute remote binary downloads or start background shell processes.
    if not caddy_installed:
        results["needs_caddy_install"] = True
        message = (
            f"Configuration created for {domain}! "
            "Please install Caddy from https://caddyserver.com/download, "
            "then run 'caddy run' in your project directory."
        )
    else:
        message = f"HTTPS configured for {domain}! Start Caddy manually with: caddy run"

    logger.info(f"HTTPS setup completed by {current_user.email} for domain {domain}")

    return {
        "success": True,
        "message": message,
        **results
    }


@router.get("/remediate/check-caddy")
async def check_caddy_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """Check if Caddy is installed and get its version."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    import subprocess

    try:
        result = subprocess.run(
            ["caddy", "version"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return {
                "installed": True,
                "version": result.stdout.strip()
            }
        else:
            return {"installed": False, "version": None}

    except (FileNotFoundError, subprocess.SubprocessError):
        return {"installed": False, "version": None}


@router.post("/remediate/fix-dotfile-blocking")
async def fix_dotfile_blocking(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Automatically update Caddyfile to block access to dotfiles (.env, .git, etc.).

    This prevents sensitive files from being exposed through the web server.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    import subprocess

    # Find the project root and Caddyfile
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )))
    project_root = os.path.dirname(backend_dir)
    caddyfile_path = os.path.join(project_root, "Caddyfile")

    results = {
        "caddyfile_found": False,
        "caddyfile_updated": False,
        "caddy_reloaded": False,
        "errors": []
    }

    # Check if Caddyfile exists
    if not os.path.exists(caddyfile_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caddyfile not found at {caddyfile_path}. Set up HTTPS first."
        )

    results["caddyfile_found"] = True

    try:
        # Read current Caddyfile
        with open(caddyfile_path, "r") as f:
            content = f.read()

        # Check if dotfile blocking already exists
        if "handle /.env" in content or "@blocked" in content:
            logger.info("Dotfile blocking already configured in Caddyfile")
            return {
                "success": True,
                "message": "Dotfile blocking is already configured!",
                "already_configured": True,
                **results
            }

        # Add dotfile blocking rules using explicit handle blocks
        # These must come BEFORE the catch-all "handle {" block in Caddy
        dotfile_rules = """    # Security: Block access to sensitive files
    handle /.env {
        respond 404
    }
    handle /.git/* {
        respond 404
    }
    handle /backend/.env {
        respond 404
    }
"""

        # Find the catch-all "handle {" block and insert before it
        lines = content.split("\n")
        insert_index = None

        # Look for "handle {" (catch-all handle block) - it's usually the last handle
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Match "handle {" but not "handle /something {" or "handle @matcher {"
            if stripped == "handle {":
                insert_index = i
                break

        if insert_index is None:
            # Fallback: insert before the closing brace
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip() == "}":
                    insert_index = i
                    break

        if insert_index is None:
            insert_index = len(lines) - 1

        # Insert the dotfile blocking rules
        lines.insert(insert_index, dotfile_rules)
        new_content = "\n".join(lines)

        # Write updated Caddyfile
        with open(caddyfile_path, "w") as f:
            f.write(new_content)

        results["caddyfile_updated"] = True
        logger.info(f"Caddyfile updated with dotfile blocking by {current_user.email}")

        # Try to reload Caddy
        try:
            # Check if caddy is running and reload it
            import platform
            if platform.system() == "Windows":
                # Try to reload Caddy (it will pick up the new config)
                # First check if caddy is in the project root
                caddy_exe = os.path.join(project_root, "caddy.exe")
                if os.path.exists(caddy_exe):
                    reload_result = subprocess.run(
                        [caddy_exe, "reload", "--config", caddyfile_path],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=project_root
                    )
                else:
                    reload_result = subprocess.run(
                        ["caddy", "reload", "--config", caddyfile_path],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=project_root
                    )

                if reload_result.returncode == 0:
                    results["caddy_reloaded"] = True
                    logger.info("Caddy reloaded successfully")
                else:
                    # Caddy might not be running, that's OK
                    results["errors"].append("Caddy not running - restart Caddy to apply changes")
            else:
                reload_result = subprocess.run(
                    ["caddy", "reload", "--config", caddyfile_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=project_root
                )
                if reload_result.returncode == 0:
                    results["caddy_reloaded"] = True

        except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
            results["errors"].append(f"Could not reload Caddy: {str(e)[:50]}")
            # Non-fatal - user can restart manually

        logger.info(f"Dotfile blocking configured by {current_user.email}")

        if results["caddy_reloaded"]:
            message = "Dotfile blocking enabled! Caddy has been reloaded."
        else:
            message = "Dotfile blocking configured! Restart Caddy to apply changes."

        return {
            "success": True,
            "message": message,
            "requires_restart": not results["caddy_reloaded"],
            **results
        }

    except Exception as e:
        logger.error(f"Failed to configure dotfile blocking: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update Caddyfile: {str(e)}"
        )


@router.get("/remediate/{check_id}")
async def get_remediation_steps(
    check_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _gate=Depends(require_local_remediation),
):
    """
    Get detailed remediation steps for a specific check.

    Returns step-by-step instructions, code snippets, and file paths.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    # Remediation guides for each check
    remediation_guides = {
        "secret_key_not_default": {
            "title": "Fix: Weak SECRET_KEY",
            "severity": "critical",
            "estimated_time": "2 minutes",
            "can_auto_generate": True,
            "steps": [
                {
                    "step": 1,
                    "title": "Generate a Secure Key",
                    "description": "Click the button below to generate a cryptographically secure key.",
                    "action": "generate_key"
                },
                {
                    "step": 2,
                    "title": "Update Your .env File",
                    "description": "Open your backend configuration file and replace the SECRET_KEY value.",
                    "file_path": "backend/.env",
                    "code_before": "SECRET_KEY=change-this-to-a-random-secret-key-in-production",
                    "code_after": "SECRET_KEY=<your-generated-key>"
                },
                {
                    "step": 3,
                    "title": "Restart the Backend",
                    "description": "The new key takes effect after restarting the server.",
                    "command": "Ctrl+C then run start-backend.ps1 again"
                }
            ]
        },
        "secret_key_entropy": {
            "title": "Fix: SECRET_KEY Too Short",
            "severity": "warning",
            "estimated_time": "2 minutes",
            "can_auto_generate": True,
            "steps": [
                {
                    "step": 1,
                    "title": "Generate a Longer Key",
                    "description": "Generate a new key with at least 64 characters.",
                    "action": "generate_key"
                },
                {
                    "step": 2,
                    "title": "Update Your .env File",
                    "description": "Replace the existing SECRET_KEY with the longer one.",
                    "file_path": "backend/.env"
                },
                {
                    "step": 3,
                    "title": "Restart the Backend",
                    "description": "Restart to apply the new key."
                }
            ]
        },
        "https_enabled": {
            "title": "Fix: Enable HTTPS",
            "severity": "warning",
            "estimated_time": "2 minutes",
            "can_auto_fix_https": True,
            "steps": [
                {
                    "step": 1,
                    "title": "Enter Your Domain",
                    "description": "Tell us what domain you want to use (e.g., filaops.local, mycompany.com)."
                },
                {
                    "step": 2,
                    "title": "We'll Install Caddy",
                    "description": "We'll automatically install Caddy (a secure web server) if it's not already installed."
                },
                {
                    "step": 3,
                    "title": "Configure & Start",
                    "description": "We'll create the configuration and start the HTTPS server for you."
                },
                {
                    "step": 4,
                    "title": "Desktop Shortcut",
                    "description": "We'll create a 'Start FilaOps' shortcut on your desktop to launch everything with one click."
                }
            ]
        },
        "cors_not_wildcard": {
            "title": "Fix: CORS Configuration",
            "severity": "warning",
            "estimated_time": "5 minutes",
            "can_auto_generate": False,
            "steps": [
                {
                    "step": 1,
                    "title": "Open Your .env File",
                    "description": "Find the ALLOWED_ORIGINS setting.",
                    "file_path": "backend/.env"
                },
                {
                    "step": 2,
                    "title": "Update Allowed Origins",
                    "description": "Replace localhost with your production domain(s):",
                    "code_before": 'ALLOWED_ORIGINS=["http://localhost:5173"]',
                    "code_after": 'ALLOWED_ORIGINS=["https://yourdomain.com"]'
                },
                {
                    "step": 3,
                    "title": "Restart the Backend",
                    "description": "Restart to apply the new CORS settings."
                }
            ]
        },
        "admin_password_changed": {
            "title": "Fix: Change Admin Password",
            "severity": "critical",
            "estimated_time": "1 minute",
            "can_auto_generate": False,
            "steps": [
                {
                    "step": 1,
                    "title": "Go to Team Members",
                    "description": "Navigate to Admin > Team Members in the sidebar.",
                    "action": "navigate",
                    "navigate_to": "/admin/users"
                },
                {
                    "step": 2,
                    "title": "Edit Admin User",
                    "description": "Find the admin user and click Edit."
                },
                {
                    "step": 3,
                    "title": "Set a Strong Password",
                    "description": "Use a password with at least 12 characters, including uppercase, lowercase, numbers, and symbols."
                }
            ]
        },
        "dependencies_secure": {
            "title": "Fix: Check Dependencies for Vulnerabilities",
            "severity": "warning",
            "estimated_time": "2 minutes",
            "can_auto_fix_dependencies": True,
            "steps": [
                {
                    "step": 1,
                    "title": "Scan for Vulnerabilities",
                    "description": "We'll scan all installed packages for known security issues."
                },
                {
                    "step": 2,
                    "title": "Upgrade Vulnerable Packages",
                    "description": "Automatically upgrade any packages with known vulnerabilities."
                },
                {
                    "step": 3,
                    "title": "Restart the Backend",
                    "description": "Restart to apply the updated packages."
                }
            ]
        },
        "rate_limiting_enabled": {
            "title": "Fix: Enable Rate Limiting",
            "severity": "warning",
            "estimated_time": "1 minute",
            "can_auto_fix_rate_limiting": True,
            "steps": [
                {
                    "step": 1,
                    "title": "Install SlowAPI",
                    "description": "We'll install the rate limiting library for you."
                },
                {
                    "step": 2,
                    "title": "Restart the Backend",
                    "description": "FilaOps will automatically detect and enable rate limiting."
                }
            ]
        },
        "backup_configured": {
            "title": "Fix: Configure Database Backups",
            "severity": "warning",
            "estimated_time": "10 minutes",
            "can_auto_generate": False,
            "steps": [
                {
                    "step": 1,
                    "title": "Create Backup Script",
                    "description": "Create a script to backup your PostgreSQL database:",
                    "code_snippet": """@echo off
set BACKUP_DIR=C:\\backups\\filaops
set TIMESTAMP=%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%
pg_dump -U postgres -d filaops > "%BACKUP_DIR%\\filaops_%TIMESTAMP%.sql"
"""
                },
                {
                    "step": 2,
                    "title": "Schedule Daily Backups",
                    "description": "Use Windows Task Scheduler to run the script daily.",
                    "docs_url": "https://www.postgresql.org/docs/current/backup-dump.html"
                }
            ]
        },
        "env_file_not_exposed": {
            "title": "Fix: Block .env File Access",
            "severity": "critical",
            "estimated_time": "30 seconds",
            "can_auto_fix_dotfiles": True,
            "steps": [
                {
                    "step": 1,
                    "title": "Update Caddy Configuration",
                    "description": "We'll add a rule to your Caddyfile that blocks access to sensitive files like .env and .git folders."
                },
                {
                    "step": 2,
                    "title": "Reload Caddy",
                    "description": "We'll automatically reload Caddy to apply the changes."
                }
            ]
        }
    }

    if check_id not in remediation_guides:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No remediation guide found for check: {check_id}"
        )

    return remediation_guides[check_id]
