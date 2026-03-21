"""
Company Settings Model

Stores company-wide settings including:
- Company name, address, contact info
- Logo image
- Tax configuration
- Quote/Invoice settings
"""
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, LargeBinary, func

from app.db.base import Base


class CompanySettings(Base):
    """
    Company-wide settings (singleton table - only one row)
    """
    __tablename__ = "company_settings"

    id = Column(Integer, primary_key=True, default=1)

    # Company Info
    company_name = Column(String(255), nullable=True)
    company_address_line1 = Column(String(255), nullable=True)
    company_address_line2 = Column(String(255), nullable=True)
    company_city = Column(String(100), nullable=True)
    company_state = Column(String(50), nullable=True)
    company_zip = Column(String(20), nullable=True)
    company_country = Column(String(100), nullable=True, default="USA")
    company_phone = Column(String(30), nullable=True)
    company_email = Column(String(255), nullable=True)
    company_website = Column(String(255), nullable=True)

    # Logo (stored as binary, or file path)
    logo_data = Column(LargeBinary, nullable=True)  # PNG/JPG binary data
    logo_filename = Column(String(255), nullable=True)
    logo_mime_type = Column(String(100), nullable=True)

    # Tax Configuration
    tax_enabled = Column(Boolean, nullable=False, default=False)
    tax_rate = Column(Numeric(5, 4), nullable=True)  # e.g., 0.0825 for 8.25%
    tax_name = Column(String(50), nullable=True, default="Sales Tax")  # "Sales Tax", "VAT", etc.
    tax_registration_number = Column(String(100), nullable=True)  # Tax ID, VAT number, etc.

    # Quote Settings
    default_quote_validity_days = Column(Integer, nullable=False, default=30)
    quote_terms = Column(String(2000), nullable=True)  # Terms & conditions text
    quote_footer = Column(String(1000), nullable=True)  # Footer text for quotes

    # Invoice Settings (for future)
    invoice_prefix = Column(String(20), nullable=True, default="INV")
    invoice_terms = Column(String(2000), nullable=True)

    # Accounting Settings
    fiscal_year_start_month = Column(Integer, nullable=True, default=1)  # 1=January
    accounting_method = Column(String(20), nullable=True, default="cash")  # cash or accrual
    currency_code = Column(String(10), nullable=True, default="USD")

    # Locale / i18n
    # BCP-47 locale string — controls number/date formatting (e.g. "en-US", "fr-CA", "ar-SA")
    locale = Column(String(20), nullable=True, default="en-US")

    # Timezone
    # IANA timezone name (e.g., "America/New_York", "America/Chicago")
    timezone = Column(String(50), nullable=True, default="America/New_York")

    # Production/Business Hours Settings
    # Default business hours for non-printer operations (8am-4pm, Mon-Fri)
    business_hours_start = Column(Integer, nullable=True, default=8)  # Hour of day (0-23), default 8am
    business_hours_end = Column(Integer, nullable=True, default=16)  # Hour of day (0-23), default 4pm
    business_days_per_week = Column(Integer, nullable=True, default=5)  # 5 = Mon-Fri
    # Work days as comma-separated list: "0,1,2,3,4" for Mon-Fri (0=Monday, 6=Sunday)
    business_work_days = Column(String(20), nullable=True, default="0,1,2,3,4")  # Mon-Fri

    # AI Configuration (for invoice parsing, etc.)
    # Provider: 'anthropic', 'ollama', or None (disabled)
    ai_provider = Column(String(20), nullable=True)
    # API key for Anthropic (stored - consider encryption in production)
    ai_api_key = Column(String(500), nullable=True)
    # Ollama URL (default: http://localhost:11434)
    ai_ollama_url = Column(String(255), nullable=True, default="http://localhost:11434")
    # Ollama model name (default: llama3.2)
    ai_ollama_model = Column(String(100), nullable=True, default="llama3.2")
    # Anthropic model name (default: claude-sonnet-4-20250514)
    ai_anthropic_model = Column(String(100), nullable=True, default="claude-sonnet-4-20250514")
    # Block external AI services (force local-only for data privacy)
    external_ai_blocked = Column(Boolean, nullable=False, default=False)

    # Pricing
    default_margin_percent = Column(Numeric(5, 2), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<CompanySettings(company_name={self.company_name})>"
