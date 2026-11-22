import ipaddress
import socket
from urllib.parse import urlsplit
from typing import Optional, Set
from backend.app.core.config import settings
from backend.app.core.errors import ShipProofException
from backend.app.core.logging import get_logger

logger = get_logger("url_validator")

ALLOWED_SCHEMES = {"http", "https"}

# Cloud metadata hostnames and IPs strictly prohibited across all environments
BLOCKED_METADATA_HOSTS: Set[str] = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.goog",
    "100.100.100.200",
}

# Dedicated metadata network ranges (blocked in ALL modes including development)
METADATA_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),       # IPv4 link-local / AWS / GCP / Azure metadata
    ipaddress.ip_network("100.100.100.200/32"),   # Alibaba cloud metadata
    ipaddress.ip_network("fe80::/10"),            # IPv6 link-local
]

# IPv4 / IPv6 network blocks considered private / internal (blocked in production)
PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),        # Unique Local Address (IPv6)
    ipaddress.ip_network("fe80::/10"),       # Link-local (IPv6)
    ipaddress.ip_network("::ffff:0:0/96"),   # IPv4-mapped IPv6
    ipaddress.ip_network("2001:db8::/32"),   # Documentation prefix
    ipaddress.ip_network("100::/64"),        # Discard prefix
]

def check_ip_in_networks(ip_str: str, networks: list) -> bool:
    """
    Checks if an IP string belongs to any network in the provided list.
    Correctly unpacks and verifies IPv4-mapped IPv6 addresses.
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        # Check direct containment
        for net in networks:
            if ip_obj in net:
                return True

        # If IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1 or ::ffff:169.254.169.254)
        if ip_obj.version == 6 and ip_obj.ipv4_mapped:
            mapped = ip_obj.ipv4_mapped
            for net in networks:
                if mapped in net:
                    return True
        return False
    except ValueError:
        return False

def validate_target_url(
    url_str: str,
    allow_local: Optional[bool] = None
) -> str:
    """
    Validates user-supplied target URLs to prevent SSRF, non-HTTP protocol smuggling,
    cloud metadata exfiltration, and internal network scanning.

    - Scheme must strictly be http or https (blocks file://, gopher://, javascript:, ftp://).
    - Link-local and cloud metadata endpoints are ALWAYS blocked regardless of environment.
    - Handles alternative IP representations (hex, octal, decimal, IPv4-mapped IPv6).
    - Normalizes IDN / punycode hostnames and strips trailing FQDN dots.
    - In production (allow_local=False), all private IP ranges and loopbacks are rejected.
    - In development (allow_local=True), local targets like the Sample Store are permitted.
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

    raw_hostname = parts.hostname
    if not raw_hostname:
        raise ShipProofException("Target URL must include a valid hostname or IP address", status_code=422)

    # Normalize hostname (strip trailing FQDN dot, lower, punycode IDN)
    hostname_clean = raw_hostname.rstrip(".").lower()
    try:
        hostname_clean = hostname_clean.encode("idna").decode("ascii")
    except Exception:
        pass  # Keep as-is if already ASCII

    # Port range validation
    try:
        if parts.port is not None:
            if parts.port < 1 or parts.port > 65535:
                raise ShipProofException(f"Invalid port '{parts.port}': port must be between 1 and 65535", status_code=422)
    except ValueError as ve:
        raise ShipProofException(f"Invalid port in URL: {str(ve)}", status_code=422)

    target_port = parts.port or (443 if scheme == "https" else 80)

    # 1. Immediate static hostname metadata check
    if hostname_clean in BLOCKED_METADATA_HOSTS:
        raise ShipProofException(
            f"Access to cloud metadata endpoint '{raw_hostname}' is strictly prohibited",
            status_code=422
        )

    # Direct IP link-local / metadata check if literal
    try:
        ip_obj = ipaddress.ip_address(hostname_clean)
        if ip_obj.is_link_local or check_ip_in_networks(str(ip_obj), METADATA_NETWORKS):
            raise ShipProofException(
                f"Access to link-local / metadata address '{raw_hostname}' is strictly prohibited",
                status_code=422
            )
    except ValueError:
        pass  # Not a standard IP literal, will be resolved via DNS

    # Determine environment policy
    if allow_local is None:
        allow_local = settings.ALLOW_LOCAL_TARGETS and (
            settings.ENVIRONMENT.lower() != "production" or settings.DEPLOYMENT_MODE == "trusted_single_tenant"
        )

    # 2. DNS resolution and canonical IP analysis
    # Even in development mode, we resolve to ensure the target is NOT pointing to metadata
    try:
        addr_info = socket.getaddrinfo(hostname_clean, target_port, proto=socket.IPPROTO_TCP)
        resolved_ips = {item[4][0] for item in addr_info}
    except socket.gaierror as dns_err:
        logger.warning(f"DNS resolution failed for target host '{hostname_clean}': {dns_err}")
        raise ShipProofException(
            f"Failed to resolve target hostname '{raw_hostname}': {dns_err}",
            status_code=422
        )

    # Enforce metadata prohibition across ALL resolved IPs (Universal rule)
    for rip in resolved_ips:
        if check_ip_in_networks(rip, METADATA_NETWORKS) or rip in BLOCKED_METADATA_HOSTS:
            raise ShipProofException(
                f"Access to cloud metadata / link-local endpoint ({raw_hostname} -> {rip}) is strictly prohibited",
                status_code=422
            )

    # 3. Production / Beta Private Network Enforcement
    if not allow_local:
        if hostname_clean in ("localhost", "localhost.localdomain") or hostname_clean.endswith(".localhost"):
            raise ShipProofException(
                "SSRF Protection: Access to loopback addresses is disabled in production",
                status_code=422
            )

        for rip in resolved_ips:
            if check_ip_in_networks(rip, PRIVATE_NETWORKS):
                raise ShipProofException(
                    f"SSRF Protection: Target '{raw_hostname}' resolves to private/internal IP {rip}, which is prohibited in production",
                    status_code=422
                )

    return url_str
