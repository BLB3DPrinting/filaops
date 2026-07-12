"""
Printer Discovery Base Adapter

Abstract base class for brand-specific printer discovery adapters.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from .models import (
    DiscoveredPrinter,
    PrinterStatus,
    PrinterCapabilities,
    PrinterConnectionConfig,
)


class PrinterDiscoveryAdapter(ABC):
    """
    Abstract base class for printer discovery adapters.

    Each printer brand implements this interface to provide:
    - Network discovery (mDNS, SSDP, etc.)
    - Cloud API discovery (optional)
    - Status checking
    - Connection testing
    """

    @property
    @abstractmethod
    def brand_name(self) -> str:
        """Human-readable brand name"""
        pass

    @property
    @abstractmethod
    def brand_code(self) -> str:
        """Brand code for database storage (e.g., 'bambulab')"""
        pass

    @abstractmethod
    async def discover_local(self, timeout_seconds: float = 5.0) -> List[DiscoveredPrinter]:
        """
        Discover printers on the local network.

        Uses brand-specific discovery protocols (SSDP, mDNS, etc.)

        Args:
            timeout_seconds: How long to wait for discovery responses

        Returns:
            List of discovered printers
        """
        pass

    async def discover_cloud(
        self,
        credentials: Dict[str, Any]
    ) -> List[DiscoveredPrinter]:
        """
        Discover printers via cloud API.

        Not all brands support this - default returns empty list.

        Args:
            credentials: Brand-specific credentials (API key, tokens, etc.)

        Returns:
            List of discovered printers
        """
        return []

    @abstractmethod
    async def test_connection(
        self,
        config: PrinterConnectionConfig
    ) -> tuple[bool, Optional[str]]:
        """
        Test if we can connect to a printer with given config.

        Args:
            config: Connection configuration to test

        Returns:
            Tuple of (success, error_message)
            - success: True if connection works
            - error_message: None if success, otherwise error description
        """
        pass

    @abstractmethod
    async def get_status(
        self,
        config: PrinterConnectionConfig
    ) -> Optional[PrinterStatus]:
        """
        Get current printer status.

        Args:
            config: Connection configuration

        Returns:
            Current status or None if unreachable
        """
        pass

    async def get_capabilities(
        self,
        config: PrinterConnectionConfig
    ) -> Optional[PrinterCapabilities]:
        """
        Query printer for its capabilities.

        Default implementation returns None (use known model data instead).
        Override for brands that report capabilities via API.

        Args:
            config: Connection configuration

        Returns:
            Capabilities if queryable, None otherwise
        """
        return None

    def get_connection_fields(self) -> List[Dict[str, Any]]:
        """
        Get the form fields needed for this brand's connection config.

        Returns list of field definitions for the frontend form.
        Override to customize fields per brand.
        """
        return [
            {
                "name": "ip_address",
                "label": "IP Address",
                "type": "text",
                "required": True,
                "placeholder": "192.168.1.100",
            },
        ]

    def get_supported_models(self) -> List[Dict[str, Any]]:
        """
        Get list of known models for this brand.

        Returns list of {"value": "model_code", "label": "Display Name"} plus
        optional "capabilities" (dict) and "discontinued" (bool) keys.
        Override to provide brand-specific model list.
        """
        return []
