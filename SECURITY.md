# Security Policy

## Official Repository

The **only** official source for FilaOps is:

**[github.com/BLB3DPrinting/filaops](https://github.com/BLB3DPrinting/filaops)**

Malicious forks and repackaged copies of FilaOps exist. We will **never** ask you to download zip files from `raw.githubusercontent.com` links. If you encounter this, it is malware. Always verify releases at: [github.com/BLB3DPrinting/filaops/releases](https://github.com/BLB3DPrinting/filaops/releases)

---

## Supported Versions

| Version | Supported |
| ------- | --------- |
| Latest `main` branch | Active security updates |
| Latest tagged release | Active security updates |
| Older releases | No backported fixes — please upgrade |

We recommend always running the latest release. Security patches are applied to `main` and included in the next tagged release.

---

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub Issues, Discussions, or Pull Requests.**

If you discover a security vulnerability in FilaOps, we appreciate your help in disclosing it responsibly.

### How to Report

1. **GitHub Private Vulnerability Reporting (Preferred)**
   Use GitHub's built-in private reporting at:
   [github.com/BLB3DPrinting/filaops/security/advisories/new](https://github.com/BLB3DPrinting/filaops/security/advisories/new)

2. **Email**
   Send details to: **security@blb3dprinting.com**

### What to Include

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof of concept
- The version(s) of FilaOps affected
- Any suggested fix or mitigation (optional but appreciated)

### What to Expect

- **Acknowledgment** within 48 hours of your report
- **Initial assessment** within 5 business days
- **Status updates** at least every 7 days until resolution
- **Credit** in release notes (unless you prefer to remain anonymous)

We will work with you to understand the issue and coordinate a fix before any public disclosure.

### Scope

The following are **in scope** for security reports:

- Authentication and authorization bypasses
- SQL injection, XSS, CSRF, and other injection attacks
- Sensitive data exposure (API keys, credentials, PII leaks)
- Remote code execution
- Privilege escalation
- Insecure default configurations that could lead to data loss
- Dependency vulnerabilities with a viable exploit path

The following are **out of scope**:

- Vulnerabilities in third-party services (report directly to those vendors)
- Social engineering attacks against BLB3D team members
- Denial of service (DoS) attacks against self-hosted instances you don't own
- Reports from automated scanners without a demonstrated exploit
- Issues that require physical access to the host system

---

## Security Practices

### For Self-Hosted Deployments

FilaOps is self-hosted software. You are responsible for securing your deployment environment. We recommend:

- **Keep FilaOps updated** — always run the latest release
- **Use HTTPS** — never expose FilaOps over plain HTTP
- **Restrict database access** — do not expose PostgreSQL publicly
- **Use strong credentials** — change all default passwords and API keys
- **Back up regularly** — maintain encrypted, off-site backups
- **Monitor access logs** — review for anomalous activity
- **Rotate API keys** — at least quarterly, or immediately if compromised

### In the Codebase

- Environment variables for all secrets (never committed to source)
- Constant-time comparison for API key validation
- Rate limiting on authentication and public-facing endpoints
- Input validation and parameterized database queries
- Dependency scanning via Dependabot
- Static analysis via CodeQL (Python + JavaScript/TypeScript)

---

## Compliance Note

FilaOps is designed to support regulated manufacturing environments (ISO 13485, FDA 21 CFR Part 820, AS9100, etc.). However, **FilaOps itself is not certified** against these standards. Organizations operating in regulated industries are responsible for validating FilaOps within their own quality management systems, including IQ/OQ/PQ protocols as appropriate.

---

## Disclosure Policy

We follow a **coordinated disclosure** approach:

1. Reporter submits vulnerability privately
2. We confirm and assess severity
3. We develop and test a fix
4. We release the fix and publish a security advisory
5. Reporter is credited (if desired) in the advisory

We aim to resolve critical vulnerabilities within **14 days** and high-severity issues within **30 days**. We ask that reporters allow us reasonable time to address issues before any public disclosure.

---

## Contact

- **Security reports**: security@blb3dprinting.com
- **General inquiries**: info@blb3dprinting.com
- **Community**: [Discord](https://discord.gg/filaops)

Thank you for helping keep FilaOps and its users safe.
