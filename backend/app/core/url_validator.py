import ipaddress
import socket
from urllib.parse import urlsplit
from typing import Optional
from backend.app.core.config import settings
from backend.app.core.errors import ShipProofException
from backend.app.core.logging import get_logger

logger = get_logger("url_validator")

ALLOWED_SCHEMES = {"http", "https"}

# Cloud metadata addresses and hostnames that are strictly dangerous in any environment
BLOCKED_METADATA_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.goog",
    "100.100.100.200",
}

# IPv4 / IPv6 network blocks considered private / internal
PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / Cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),        # Unique Local Address (IPv6)
    ipaddress.ip_network("fe80::/10"),       # Link-local (IPv6)
]

def is_ip_in_networks(ip_str: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        return any(ip_obj in net for net in networks)
    except ValueError:
        return False

def validate_target_url(
    url_str: str,
    allow_local: Optional[bool] = None
) -> str:
    """
    Validates user-supplied target URLs to prevent SSRF, non-HTTP protocol smuggling,
    cloud metadata exfiltration, and internal network scanning.

    In development (allow_local=True), loopback and local private networks are permitted
    to support the Sample Store demo, while metadata endpoints and dangerous schemes remain blocked.

    In production (allow_local=False), all private IP ranges and loopbacks are rejected.
    """
    if not url_str or not isinstance(url_str, str):
        raise ShipProofException("A valid target_url must be provided", status_code=422)

    url_str = url_str.strip()

    try:
        parts = urlsplit(url_str)
    except Exception as e:
        raise ShipProofException(f"Malformed URL: {str(e)}", status_code=422)

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ShipProofException(
            f"Invalid URL scheme '{scheme}': only HTTP and HTTPS protocols are permitted",
            status_code=422
        )

    hostname = parts.hostname
    if not hostname:
        raise ShipProofException("Target URL must include a valid hostname or IP address", status_code=422)

    hostname_lower = hostname.lower()

    # Port range validation
    try:
        if parts.port is not None:
            if parts.port < 1 or parts.port > 65535:
                raise ShipProofException(f"Invalid port '{parts.port}': port must be between 1 and 65535", status_code=422)
    except ValueError as ve:
        raise ShipProofException(f"Invalid port in URL: {str(ve)}", status_code=422)

    # 1. Cloud Metadata protection (ALWAYS blocked in all environments)
    if hostname_lower in BLOCKED_METADATA_HOSTS:
        raise ShipProofException(
            f"Access to cloud metadata endpoint '{hostname}' is strictly prohibited",
            status_code=422
        )

    # Check if hostname directly parses as an IP in the link-local metadata range
    try:
        ip_obj = ipaddress.ip_address(hostname_lower)
        if ip_obj.is_link_local:
            raise ShipProofException(
                f"Access to link-local / metadata address '{hostname}' is strictly prohibited",
                status_code=422
            )
    except ValueError:
        pass  # Not an IP literal

    # Determine whether local / private targets are permitted
    if allow_local is None:
        allow_local = settings.ALLOW_LOCAL_TARGETS and settings.ENVIRONMENT.lower() != "production"

    if not allow_local:
        # Production mode: reject localhost, loopback, and private IPv4/IPv6 ranges
        if hostname_lower in ("localhost", "localhost.localdomain") or hostname_lower.endswith(".localhost"):
            raise ShipProofException(
                "SSRF Protection: Access to loopback addresses is disabled in production",
                status_code=422
            )

        # Resolve hostname to check underlying IP addresses against private networks
        try:
            addr_info = socket.getaddrinfo(hostname_lower, parts.port or 80, proto=socket.IPPROTO_TCP)
            resolved_ips = {item[4][0] for item in addr_info}
            for rip in resolved_ips:
                if is_ip_in_networks(rip, PRIVATE_NETWORKS):
                    raise ShipProofException(
                        f"SSRF Protection: Target '{hostname}' resolves to private/internal IP {rip}, which is prohibited in production",
                        status_code=422
                    )
        except socket.gaierror as dns_err:
            logger.warning(f"DNS resolution failed for target host '{hostname}': {dns_err}")
            raise ShipProofException(
                f"Failed to resolve target hostname '{hostname}': {dns_err}",
                status_code=422
            )

    return url_str
