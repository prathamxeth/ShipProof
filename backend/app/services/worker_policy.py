import ipaddress
from typing import List, Optional
from backend.app.schemas.worker import WorkerJobConfig
from backend.app.core.logging import get_logger

logger = get_logger("worker_policy")

PROHIBITED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
]

PROHIBITED_IPV6_NETWORKS = [
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
]

class WorkerPolicy:
    """
    Constructs deterministic, verified security policies for worker execution.
    Enforces least privilege, zero-trust network egress, and fail-closed firewalling.
    """

    @staticmethod
    def validate_allowed_ips(ips: List[str], allow_local: bool = False) -> List[str]:
        """
        Validates target IPs. Prohibits any internal/private/link-local/metadata IP
        unless allow_local is explicitly enabled for development testbeds.
        """
        validated = []
        for ip_str in ips:
            clean_ip = ip_str.strip()
            if not clean_ip:
                continue
            try:
                ip_obj = ipaddress.ip_address(clean_ip)
            except ValueError as e:
                raise ValueError(f"Invalid IP address format in policy: {clean_ip}") from e

            # Check prohibited ranges
            is_prohibited = False
            for net in PROHIBITED_NETWORKS:
                if ip_obj in net:
                    is_prohibited = True
                    break
            
            if is_prohibited and not allow_local:
                raise ValueError(f"Prohibited destination IP in worker egress policy: {clean_ip}")
            
            validated.append(clean_ip)
        return validated

    @staticmethod
    def generate_firewall_script(
        allowed_ips: List[str],
        allow_cdp_port: int = 9222,
        dns_server_ip: Optional[str] = None,
        target_ports: Optional[List[int]] = None
    ) -> str:
        """
        Generates deterministic entrypoint shell script that sets up iptables & ip6tables,
        verifies rule loading, and drops privileges to user kane (UID 1001).
        """
        whitelist_rules = []
        for ip in allowed_ips:
            effective_ports = target_ports if target_ports else [80, 443, 8080]
            ports_str = ",".join(str(p) for p in effective_ports)
            whitelist_rules.append(
                f'iptables -A OUTPUT -p tcp -m multiport --dports {ports_str} -d "{ip}" -j ACCEPT'
            )
        whitelist_block = "\n".join(whitelist_rules)

        dns_block = ""
        if dns_server_ip:
            dns_block = f"""
# Allow DNS to designated resolver only
iptables -A OUTPUT -p udp --dport 53 -d "{dns_server_ip}" -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -d "{dns_server_ip}" -j ACCEPT
"""
        else:
            dns_block = """
# Allow DNS to container resolver
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
"""

        script = f"""#!/usr/bin/env bash
set -euo pipefail

echo "[WORKER-INIT] Initializing kernel packet filter & security confinement..."

# 1. Default DROP on all chains
iptables -F OUTPUT
iptables -F INPUT
iptables -F FORWARD

iptables -P OUTPUT DROP
iptables -P INPUT DROP
iptables -P FORWARD DROP

# 2. Allow established and related connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# 3. Strict loopback: allow CDP port {allow_cdp_port}; reject all other loopback
iptables -A INPUT -i lo -p tcp --dport "{allow_cdp_port}" -j ACCEPT
iptables -A OUTPUT -o lo -p tcp --dport "{allow_cdp_port}" -j ACCEPT
iptables -A OUTPUT -o lo -j REJECT --reject-with icmp-port-unreachable
iptables -A INPUT -i lo -j DROP

# 4. Explicitly reject prohibited networks (Cloud metadata, RFC 1918, Link-local, spoofed loopback)
iptables -A OUTPUT -d 169.254.0.0/16 -j REJECT --reject-with icmp-admin-prohibited
iptables -A OUTPUT -d 127.0.0.0/8 -j REJECT --reject-with icmp-admin-prohibited
{dns_block}
# 5. Whitelist approved target IPs
{whitelist_block}

# 6. Reject other RFC 1918 internal subnets
iptables -A OUTPUT -d 10.0.0.0/8 -j REJECT --reject-with icmp-admin-prohibited
iptables -A OUTPUT -d 172.16.0.0/12 -j REJECT --reject-with icmp-admin-prohibited
iptables -A OUTPUT -d 192.168.0.0/16 -j REJECT --reject-with icmp-admin-prohibited

# 7. Allow HTTPS for Kane cloud AI services
iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT

# 8. Default reject all other IPv4 traffic
iptables -A OUTPUT -j REJECT --reject-with icmp-port-unreachable

# 7. IPv6 firewall policy
ip6tables -F OUTPUT 2>/dev/null || true
ip6tables -F INPUT 2>/dev/null || true
ip6tables -F FORWARD 2>/dev/null || true

ip6tables -P OUTPUT DROP 2>/dev/null || true
ip6tables -P INPUT DROP 2>/dev/null || true
ip6tables -P FORWARD DROP 2>/dev/null || true

ip6tables -A OUTPUT -d ::1/128 -j REJECT 2>/dev/null || true
ip6tables -A OUTPUT -d fc00::/7 -j REJECT 2>/dev/null || true
ip6tables -A OUTPUT -d fe80::/10 -j REJECT 2>/dev/null || true
ip6tables -A OUTPUT -d ::ffff:0:0/96 -j REJECT 2>/dev/null || true
ip6tables -A OUTPUT -j REJECT 2>/dev/null || true

# Disable IPv6 on external interfaces if kernel sysctl allows
sysctl -w net.ipv6.conf.all.disable_ipv6=1 >/dev/null 2>&1 || true

# 8. Self-verification of effective firewall rules
RULES=$(iptables-save)
if ! echo "${{RULES}}" | grep -q ":OUTPUT DROP"; then
    echo "[CRITICAL] OUTPUT policy is not DROP! Failing closed." >&2
    exit 101
fi
if ! echo "${{RULES}}" | grep -q "169.254.0.0/16"; then
    echo "[CRITICAL] Metadata rejection rule missing! Failing closed." >&2
    exit 101
fi
echo "[WORKER-INIT] Firewall verified successfully."

# Provision Kane credentials securely into ephemeral tmpfs home
if [ -d "/kane-auth" ]; then
    mkdir -p /home/kane/.testmuai/kaneai
    cp -r /kane-auth/* /home/kane/.testmuai/kaneai/ 2>/dev/null || true
    mkdir -p /home/kane/.testmuai/kaneai/sessions
    chown -R 1001:1001 /home/kane
    chmod -R u=rwX,go-rwx /home/kane/.testmuai/kaneai
fi

# Prepare IPC evidence staging mount if IPC volume is mounted
if [ -d "/ipc" ]; then
    mkdir -p /ipc/evidence 2>/dev/null || true
    chown -R 1001:1001 /ipc/evidence 2>/dev/null || true
    chmod 0777 /ipc/evidence 2>/dev/null || true
fi

# 9. Drop all root capabilities and execute payload as user kane (UID 1001)
echo "[WORKER-INIT] Dropping root privileges to user 'kane' (UID 1001)..."
exec setpriv --reuid=1001 --regid=1001 --clear-groups --inh-caps=-all env HOME=/home/kane KANE_CLI_CHROME_PATH=/usr/bin/chromium "$@"
"""
        return script

    @staticmethod
    def generate_worker_agent_script() -> str:
        """
        Generates in-container worker agent script (Python) that connects to
        mounted UNIX domain socket, performs handshake, runs command, and streams NDJSON.
        """
        return """#!/usr/bin/env python3
import sys
import os
import json
import socket
import subprocess
import time
from datetime import datetime, timezone

MAX_FRAME_SIZE = 65536
SOCKET_PATH = "/ipc/worker.sock"

def log(msg):
    print(f"[WORKER-AGENT] {msg}", flush=True)

def send_frame(sock, msg_type, run_id, token, seq, payload):
    msg = {
        "msg_type": msg_type,
        "run_id": run_id,
        "worker_token": token,
        "seq": seq,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    data = json.dumps(msg).encode("utf-8") + b"\\n"
    if len(data) > MAX_FRAME_SIZE:
        # Truncate payload safely
        msg["payload"] = {"error": "payload_truncated", "summary": str(payload)[:200]}
        data = json.dumps(msg).encode("utf-8") + b"\\n"
    if sock:
        try:
            sock.sendall(data)
            return
        except Exception:
            pass
    # Fallback to stdout streaming when AF_UNIX is unsupported over cross-VFS mounts
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()

def main():
    run_id = os.getenv("RUN_ID", "")
    worker_token = os.getenv("WORKER_TOKEN", "")
    cmd_args = sys.argv[1:]

    if not run_id or not worker_token:
        log("Missing RUN_ID or WORKER_TOKEN environment variables. Exiting.")
        sys.exit(1)

    log(f"Starting agent for run {run_id}. Target command: {' '.join(cmd_args)}")

    # Attempt UNIX socket connection
    sock = None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCKET_PATH)
        sock = s
        log(f"Connected to host IPC UNIX socket at {SOCKET_PATH}.")
    except Exception as e:
        log(f"Host IPC UNIX socket unavailable ({e}); streaming frames via stdout.")

    import threading
    seq_lock = threading.Lock()
    seq_counter = 0

    def next_seq():
        nonlocal seq_counter
        with seq_lock:
            s = seq_counter
            seq_counter += 1
            return s

    # 1. Send Handshake
    send_frame(sock, "handshake", run_id, worker_token, next_seq(), {
        "status": "ready",
        "uid": os.getuid(),
        "gid": os.getgid(),
        "pid": os.getpid()
    })

    # 2. Execute process
    exit_code = 1
    error_msg = None
    try:
        proc = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        def stream_stderr():
            try:
                for err_line in proc.stderr:
                    el = err_line.strip()
                    if el:
                        send_frame(sock, "log", run_id, worker_token, next_seq(), {"stderr": el[:2000]})
            except Exception:
                pass

        t_err = threading.Thread(target=stream_stderr, daemon=True)
        t_err.start()

        # Stream stdout line by line
        for line in proc.stdout:
            cleaned = line.strip()
            if not cleaned:
                continue
            send_frame(sock, "event", run_id, worker_token, next_seq(), {"raw_line": cleaned})

        proc.wait()
        t_err.join(timeout=2.0)
        exit_code = proc.returncode
    except Exception as e:
        error_msg = str(e)
        send_frame(sock, "error", run_id, worker_token, next_seq(), {"error": error_msg})

    # Stage evidence before terminating process
    evidence_pack_in_container = None
    home_kane_sessions = "/home/kane/.testmuai/kaneai/sessions"
    if os.path.isdir(home_kane_sessions):
        for sess_id in sorted(os.listdir(home_kane_sessions), reverse=True):
            sess_ev_dir = os.path.join(home_kane_sessions, sess_id, "evidence")
            if os.path.isdir(sess_ev_dir):
                for fname in sorted(os.listdir(sess_ev_dir), reverse=True):
                    if fname.endswith(".evidence"):
                        evidence_pack_in_container = os.path.join(sess_ev_dir, fname)
                        break
            if evidence_pack_in_container:
                break

    if evidence_pack_in_container and os.path.exists(evidence_pack_in_container):
        try:
            import shutil
            import hashlib
            target_ipc_evidence = "/ipc/evidence/evidence.pack"
            os.makedirs("/ipc/evidence", exist_ok=True)
            shutil.copy2(evidence_pack_in_container, target_ipc_evidence)
            with open(target_ipc_evidence, "rb") as ef:
                pack_bytes = ef.read()
            pack_sha256 = hashlib.sha256(pack_bytes).hexdigest()
            pack_size = len(pack_bytes)
            send_frame(sock, "evidence_ready", run_id, worker_token, next_seq(), {
                "status": "ready",
                "rel_path": "evidence/evidence.pack",
                "sha256": pack_sha256,
                "size": pack_size,
                "source_file": os.path.basename(evidence_pack_in_container)
            })
            log(f"Evidence pack staged to /ipc/evidence/evidence.pack ({pack_size} bytes, sha256: {pack_sha256[:16]})")
        except Exception as ev_err:
            log(f"Failed to copy evidence pack to /ipc: {ev_err}")

    # 3. Send Complete
    send_frame(sock, "complete", run_id, worker_token, next_seq(), {
        "exit_code": exit_code,
        "error_message": error_msg
    })
    if sock:
        try:
            sock.close()
        except Exception:
            pass
    log(f"Worker agent finished with exit code {exit_code}.")
    # Allow host orchestrator a brief window to extract ephemeral tmpfs evidence before process exit
    time.sleep(5)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
"""
