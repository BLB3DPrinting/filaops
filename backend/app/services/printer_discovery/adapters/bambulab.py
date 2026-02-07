"""
BambuLab Printer Discovery Adapter

Supports:
- SSDP local network discovery
- Cloud API discovery (via BambuLab account)
- MQTT status monitoring
"""

import asyncio
import logging
import socket
from typing import List, Optional, Dict, Any

from ..base import PrinterDiscoveryAdapter
from ..models import (
    DiscoveredPrinter,
    PrinterBrand,
    PrinterStatus,
    PrinterCapabilities,
    PrinterConnectionConfig,
    ConnectionType,
    KNOWN_PRINTER_MODELS,
)

logger = logging.getLogger(__name__)

# SSDP discovery constants
SSDP_MULTICAST_ADDR = "239.255.255.250"
SSDP_PORT = 1990  # BambuLab uses non-standard port
SSDP_SEARCH_TARGET = "urn:bambulab-com:device:3dprinter:1"

SSDP_DISCOVER_MSG = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_MULTICAST_ADDR}:{SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 3\r\n"
    f"ST: {SSDP_SEARCH_TARGET}\r\n"
    "\r\n"
)


class BambuLabAdapter(PrinterDiscoveryAdapter):
    """Discovery adapter for BambuLab printers (X1C, P1S, A1, etc.)"""

    @property
    def brand_name(self) -> str:
        return "BambuLab"

    @property
    def brand_code(self) -> str:
        return "bambulab"

    async def discover_local(self, timeout_seconds: float = 5.0) -> List[DiscoveredPrinter]:
        """
        Discover BambuLab printers via SSDP.

        BambuLab printers respond to SSDP discovery on port 1990.
        """
        discovered = []

        try:
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(timeout_seconds)

            # Bind to any available port
            sock.bind(("", 0))

            # Send SSDP discovery request
            logger.debug(f"Sending BambuLab SSDP discovery to {SSDP_MULTICAST_ADDR}:{SSDP_PORT}")
            sock.sendto(SSDP_DISCOVER_MSG.encode(), (SSDP_MULTICAST_ADDR, SSDP_PORT))

            # Also try direct broadcast
            sock.sendto(SSDP_DISCOVER_MSG.encode(), ("255.255.255.255", SSDP_PORT))

            # Collect responses
            end_time = asyncio.get_event_loop().time() + timeout_seconds
            while asyncio.get_event_loop().time() < end_time:
                try:
                    data, addr = sock.recvfrom(4096)
                    response = data.decode("utf-8", errors="ignore")

                    printer = self._parse_ssdp_response(response, addr[0])
                    if printer:
                        discovered.append(printer)
                        logger.info(f"Discovered BambuLab printer: {printer.name} at {addr[0]}")

                except socket.timeout:
                    break
                except Exception as e:
                    logger.debug(f"Error receiving SSDP response: {e}")
                    continue

            sock.close()

        except Exception as e:
            logger.error(f"BambuLab SSDP discovery error: {e}")

        logger.info(f"BambuLab discovery found {len(discovered)} printers")
        return discovered

    async def discover_cloud(self, credentials: Dict[str, Any]) -> List[DiscoveredPrinter]:
        """
        Discover printers via BambuLab Cloud API.

        Requires valid BambuLab account credentials.
        Note: Cloud API integration is a future enhancement.
        """
        # BambuLab cloud API integration planned (requires OAuth flow + device API)
        logger.info("BambuLab cloud discovery not yet implemented")
        return []

    async def test_connection(
        self,
        config: PrinterConnectionConfig
    ) -> tuple[bool, Optional[str]]:
        """Test connection to BambuLab printer via MQTT or HTTP"""
        if not config.ip_address:
            return False, "IP address is required"

        try:
            # Try to connect to the printer's status port
            # BambuLab printers expose a simple HTTP endpoint
            import aiohttp

            url = f"http://{config.ip_address}/api/info"
            timeout = aiohttp.ClientTimeout(total=5)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            return True, None
                        else:
                            return False, f"HTTP {response.status}"
                except aiohttp.ClientError:
                    # Try alternate test - just check if port is open
                    return await self._check_port_open(config.ip_address, 8883), None

        except ImportError:
            # aiohttp not available, fall back to socket test
            return await self._check_port_open(config.ip_address, 8883), None
        except Exception as e:
            return False, str(e)

    async def _check_port_open(self, ip: str, port: int) -> bool:
        """Simple check if a port is open"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    async def get_status(
        self,
        config: PrinterConnectionConfig
    ) -> Optional[PrinterStatus]:
        """Get printer status via MQTT or HTTP"""
        # MQTT status monitoring planned — for now just check reachability
        if not config.ip_address:
            return PrinterStatus.OFFLINE

        is_reachable = await self._check_port_open(config.ip_address, 8883)
        return PrinterStatus.IDLE if is_reachable else PrinterStatus.OFFLINE

    def get_connection_fields(self) -> List[Dict[str, Any]]:
        """BambuLab-specific connection fields"""
        return [
            {
                "name": "ip_address",
                "label": "IP Address",
                "type": "text",
                "required": True,
                "placeholder": "192.168.1.100",
                "help": "Find this in your printer's network settings",
            },
            {
                "name": "access_code",
                "label": "Access Code",
                "type": "password",
                "required": True,
                "placeholder": "12345678",
                "help": "8-digit code from printer's network settings",
            },
            {
                "name": "serial_number",
                "label": "Serial Number",
                "type": "text",
                "required": False,
                "placeholder": "01S00C123456789",
                "help": "Optional - for identification",
            },
        ]

    def get_supported_models(self) -> List[Dict[str, str]]:
        """Get list of BambuLab printer models"""
        return [
            {"value": "X1C", "label": "X1 Carbon"},
            {"value": "X1", "label": "X1"},
            {"value": "X1E", "label": "X1E"},
            {"value": "P1S", "label": "P1S"},
            {"value": "P1P", "label": "P1P"},
            {"value": "A1", "label": "A1"},
            {"value": "A1 Mini", "label": "A1 Mini"},
        ]

    def _parse_ssdp_response(self, response: str, ip_address: str) -> Optional[DiscoveredPrinter]:
        """Parse SSDP response to extract printer info"""
        try:
            headers = {}
            for line in response.split("\r\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().upper()] = value.strip()

            # Check if this is a BambuLab printer
            if "USN" not in headers:
                return None

            usn = headers.get("USN", "")
            if "bambulab" not in usn.lower():
                return None

            # Extract model and serial from USN
            # Format: uuid:XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX::urn:bambulab-com:device:3dprinter:1
            serial = None
            model = "Unknown"

            # Try to get model from DeviceId header
            device_id = headers.get("DEVMODEL", headers.get("DEVICEID", ""))
            if device_id:
                model = device_id

            # Try to extract serial from USN
            if "uuid:" in usn:
                uuid_part = usn.split("uuid:")[1].split("::")[0]
                serial = uuid_part.replace("-", "")[:15]  # BambuLab serials are ~15 chars

            # Get capabilities from known models
            model_key = f"bambulab:{model}"
            capabilities = KNOWN_PRINTER_MODELS.get(model_key, {}).get(
                "capabilities",
                PrinterCapabilities()
            )

            return DiscoveredPrinter(
                brand=PrinterBrand.BAMBULAB,
                model=model,
                name=f"BambuLab {model}" + (f" ({serial[-4:]})" if serial else ""),
                serial_number=serial,
                connection_type=ConnectionType.LOCAL,
                ip_address=ip_address,
                capabilities=capabilities,
                connection_config=PrinterConnectionConfig(ip_address=ip_address),
                discovered_via="ssdp",
                raw_data=headers,
            )

        except Exception as e:
            logger.debug(f"Error parsing SSDP response: {e}")
            return None
