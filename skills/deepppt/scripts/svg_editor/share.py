#!/usr/bin/env python3
"""
One-click share: open LAN access with a private token for annotation review.

Usage:
    python share.py <project_dir> [--port 5050]

Steps:
    1. Detect local IP
    2. Generate random token
    3. Open Windows Firewall for the port
    4. Start preview server in --share mode (bind 0.0.0.0)
    5. Print share URL (with token) and review panel URL
    6. Ctrl+C closes server and restores firewall
"""

import argparse
import os
import secrets
import socket
import string
import subprocess
import sys
import time
from pathlib import Path

# Fix Windows encoding
if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# --------------- helpers ---------------

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def generate_token(length=16):
    return ''.join(secrets.choice(string.ascii_letters + string.digits)
                   for _ in range(length))

def firewall_rule_name(port):
    return f'PPT_Master_Share_{port}'

def firewall_open(port):
    name = firewall_rule_name(port)
    r = subprocess.run(['netsh', 'advfirewall', 'firewall', 'show', 'rule',
                        f'name={name}'], capture_output=True, text=True)
    if name in r.stdout:
        return True  # already exists
    try:
        subprocess.run(['netsh', 'advfirewall', 'firewall', 'add', 'rule',
                        f'name={name}', 'dir=in', 'action=allow',
                        'protocol=TCP', f'localport={port}'],
                       check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def firewall_close(port):
    name = firewall_rule_name(port)
    r = subprocess.run(['netsh', 'advfirewall', 'firewall', 'show', 'rule',
                        f'name={name}'], capture_output=True, text=True)
    if name not in r.stdout:
        return True
    try:
        subprocess.run(['netsh', 'advfirewall', 'firewall', 'delete', 'rule',
                        f'name={name}'], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

# --------------- main ---------------

def main():
    parser = argparse.ArgumentParser(description='PPT Master Share Preview')
    parser.add_argument('project_dir', help='Project directory path')
    parser.add_argument('--port', type=int, default=5050, help='Port (default: 5050)')
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if not project.is_dir():
        print(f'[ERROR] Project not found: {project}')
        return 1

    svg_dir = project / 'svg_output'
    if not svg_dir.exists() or not list(svg_dir.glob('*.svg')):
        print('[ERROR] No SVG files in svg_output/')
        return 1

    ip = get_local_ip()
    token = generate_token()
    port = args.port

    # 1. Firewall
    print(f'[1/3] Opening firewall port {port}...')
    if firewall_open(port):
        print(f'      Port {port} opened OK')
    else:
        print(f'      [WARN] Firewall config failed (may need admin).')
        print(f'      If reviewers cannot connect, manually open port {port}.')

    # 2. Start server
    server_py = Path(__file__).resolve().parent / 'server.py'
    if not server_py.exists():
        print(f'[ERROR] server.py not found at {server_py}')
        firewall_close(port)
        return 1

    print(f'[2/3] Starting share server...')
    proc = subprocess.Popen(
        [sys.executable, str(server_py), str(project),
         '--port', str(port), '--share', '--token', token, '--no-browser'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    if proc.poll() is not None:
        print(f'[ERROR] Server failed to start (exit code: {proc.returncode})')
        firewall_close(port)
        return 1

    # 3. Print banner
    share_url = f'http://{ip}:{port}/?token={token}'
    review_url = f'http://localhost:{port}/review'

    print()
    print('=' * 60)
    print('  PPT Master - Share Preview Mode')
    print('=' * 60)
    print()
    print(f'  Share this with reviewers:')
    print(f'    {share_url}')
    print()
    print(f'  Review panel (publisher only):')
    print(f'    {review_url}')
    print()
    print(f'  Token: {token}')
    print()
    print('  Reviewers: browse slides and add annotations.')
    print('  Publisher: visit /review to approve or reject.')
    print()
    print('  Press Ctrl+C to stop sharing.')
    print('=' * 60)
    print()

    try:
        proc.wait()
    except KeyboardInterrupt:
        print()
        print('[3/3] Shutting down...')
    finally:
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill()
        firewall_close(port)
        print('      Firewall restored. Done.')

    return 0

if __name__ == '__main__':
    sys.exit(main())
