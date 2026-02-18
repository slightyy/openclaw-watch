"""
OpenClaw Watch Agent - 设备端监控代理
支持: Linux, macOS, Windows
"""
import os
import sys
import json
import time
import socket
import platform
import requests
import psutil
from datetime import datetime
from threading import Thread, Event
import logging

# ==================== 配置 ====================
NAS_URL = os.getenv("NAS_URL", "http://你的VPS IP:38889")
API_KEY = os.getenv("API_KEY", "")
REPORT_INTERVAL = int(os.getenv("REPORT_INTERVAL", "30"))

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('openclaw_watch_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== 上一轮网络流量 ====================
last_net_io = None
last_check_time = None

# ==================== OpenClaw 状态获取 ====================
def get_openclaw_status():
    """获取 OpenClaw 运行状态"""
    context_tokens = 0
    total_tokens = 0
    
    try:
        config_path = os.path.expanduser("~/.openclaw/agents/main/sessions/sessions.json")
        
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                data = json.load(f)
                sessions = data.get('sessions', data)
                for session_key, session_data in sessions.items():
                    if isinstance(session_data, dict):
                        context_tokens += session_data.get('contextTokens', 0)
                        total_tokens += session_data.get('totalTokens', 0)
            
            version = "unknown"
            try:
                result = os.popen("openclaw --version 2>/dev/null || echo 'unknown'").read().strip()
                version = result or "unknown"
            except:
                pass
            
            return {
                "openclaw_version": version,
                "openclaw_status": "running",
                "runtime": "direct",
                "model": "unknown",
                "thinking": "off",
                "context_tokens": context_tokens,
                "total_tokens": total_tokens
            }
    except Exception as e:
        logger.debug(f"获取OpenClaw状态失败: {e}")
    
    return {
        "openclaw_version": "unknown",
        "openclaw_status": "stopped",
        "runtime": "N/A",
        "model": "N/A",
        "thinking": "N/A",
        "context_tokens": 0,
        "total_tokens": 0
    }

def get_public_ip():
    """获取公网IP"""
    try:
        resp = requests.get("https://api.ipify.org", timeout=5)
        return resp.text
    except:
        return "unknown"

def get_system_resources():
    """获取系统资源占用"""
    global last_net_io, last_check_time
    
    try:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # 网络流量
        net_io = psutil.net_io_counters()
        current_time = time.time()
        
        upload_speed = 0
        download_speed = 0
        
        if last_net_io and last_check_time:
            time_diff = current_time - last_check_time
            if time_diff > 0:
                upload_speed = (net_io.bytes_sent - last_net_io.bytes_sent) / time_diff
                download_speed = (net_io.bytes_recv - last_net_io.bytes_recv) / time_diff
        
        last_net_io = net_io
        last_check_time = current_time
        
        # 公网IP
        public_ip = get_public_ip()
        
        return {
            "cpu_percent": cpu,
            "memory_percent": memory.percent,
            "memory_total": memory.total,
            "memory_used": memory.used,
            "disk_percent": disk.percent,
            "disk_total": disk.total,
            "disk_used": disk.used,
            "upload_speed": upload_speed,
            "download_speed": download_speed,
            "public_ip": public_ip
        }
    except Exception as e:
        logger.error(f"获取系统资源失败: {e}")
        return {
            "cpu_percent": 0,
            "memory_percent": 0,
            "memory_total": 0,
            "memory_used": 0,
            "disk_percent": 0,
            "disk_total": 0,
            "disk_used": 0,
            "upload_speed": 0,
            "download_speed": 0,
            "public_ip": ""
        }

# ==================== API 通信 ====================
def report_status(nas_url, api_key, status_data):
    """上报状态到NAS"""
    try:
        url = f"{nas_url}/api/report/status"
        response = requests.post(url, json=status_data, timeout=10)
        if response.status_code == 200:
            logger.debug("状态上报成功")
        else:
            logger.warning(f"状态上报失败: {response.status_code}")
    except Exception as e:
        logger.error(f"状态上报异常: {e}")

def report_error(nas_url, api_key, error_data):
    """上报错误到NAS"""
    try:
        url = f"{nas_url}/api/report/error"
        response = requests.post(url, json=error_data, timeout=10)
        if response.status_code == 200:
            logger.debug("错误日志上报成功")
        else:
            logger.warning(f"错误日志上报失败: {response.status_code}")
    except Exception as e:
        logger.error(f"错误日志上报异常: {e}")

# ==================== 主循环 ====================
class OpenClawWatchAgent:
    def __init__(self, nas_url, api_key, interval=30):
        self.nas_url = nas_url
        self.api_key = api_key
        self.interval = interval
        self.running = False
        self.stop_event = Event()
        
    def start(self):
        """启动代理"""
        if not self.api_key:
            logger.error("请设置 API_KEY 环境变量")
            sys.exit(1)
        
        logger.info(f"OpenClaw Watch Agent 启动")
        logger.info(f"NAS URL: {self.nas_url}")
        logger.info(f"上报间隔: {self.interval}秒")
        
        self.running = True
        self.stop_event.clear()
        
        status_thread = Thread(target=self.status_loop, daemon=True)
        status_thread.start()
        
        error_thread = Thread(target=self.error_loop, daemon=True)
        error_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
            
    def stop(self):
        """停止代理"""
        logger.info("正在停止 OpenClaw Watch Agent...")
        self.running = False
        self.stop_event.set()
        
    def status_loop(self):
        """状态上报循环"""
        while self.running and not self.stop_event.is_set():
            try:
                status = get_openclaw_status()
                resources = get_system_resources()
                
                report_data = {
                    "api_key": self.api_key,
                    "openclaw_version": status.get("openclaw_version"),
                    "openclaw_status": status.get("openclaw_status"),
                    "runtime": status.get("runtime"),
                    "model": status.get("model"),
                    "thinking": status.get("thinking"),
                    "cpu_percent": resources["cpu_percent"],
                    "memory_percent": resources["memory_percent"],
                    "memory_total": resources["memory_total"],
                    "memory_used": resources["memory_used"],
                    "disk_percent": resources["disk_percent"],
                    "disk_total": resources["disk_total"],
                    "disk_used": resources["disk_used"],
                    "upload_speed": resources["upload_speed"],
                    "download_speed": resources["download_speed"],
                    "public_ip": resources.get("public_ip", ""),
                    "context_tokens": status.get("context_tokens", 0),
                    "total_tokens": status.get("total_tokens", 0)
                }
                
                report_status(self.nas_url, self.api_key, report_data)
                logger.info(f"状态上报: CPU={resources['cpu_percent']:.1f}%, Memory={resources['memory_percent']:.1f}%, Net↑{resources['upload_speed']/1024:.1f}KB/s ↓{resources['download_speed']/1024:.1f}KB/s, Tokens={report_data['total_tokens']}")
                
            except Exception as e:
                logger.error(f"状态上报循环异常: {e}")
            
            self.stop_event.wait(self.interval)
    
    def error_loop(self):
        """错误日志监控循环"""
        last_position = 0
        log_file = os.path.expanduser("~/.openclaw/gateway.log")
        
        if not os.path.exists(log_file):
            possible_paths = [
                "/root/.openclaw/gateway.log",
                "~/.openclaw/logs/gateway.log"
            ]
            for p in possible_paths:
                if os.path.exists(os.path.expanduser(p)):
                    log_file = os.path.expanduser(p)
                    break
        
        while self.running and not self.stop_event.is_set():
            try:
                if os.path.exists(log_file):
                    with open(log_file, 'r') as f:
                        f.seek(last_position)
                        new_lines = f.readlines()
                        last_position = f.tell()
                        
                        for line in new_lines:
                            lower_line = line.lower()
                            if any(kw in lower_line for kw in ['error', 'exception', 'fail', 'critical']):
                                error_data = {
                                    "api_key": self.api_key,
                                    "level": "error",
                                    "message": line.strip()[:500],
                                    "source": "gateway.log"
                                }
                                report_error(self.nas_url, self.api_key, error_data)
                                
            except Exception as e:
                logger.debug(f"日志监控异常: {e}")
            
            self.stop_event.wait(10)

# ==================== 入口 ====================
def main():
    print("=" * 50)
    print("OpenClaw Watch Agent")
    print("=" * 50)
    print(f"NAS URL: {NAS_URL}")
    print(f"API Key: {API_KEY[:8]}..." if API_KEY else "API Key: 未设置!")
    print(f"上报间隔: {REPORT_INTERVAL}秒")
    print("=" * 50)
    
    if not API_KEY:
        print("\n错误: 请设置 API_KEY 环境变量")
        print("例如: export API_KEY='your-api-key'")
        sys.exit(1)
    
    agent = OpenClawWatchAgent(NAS_URL, API_KEY, REPORT_INTERVAL)
    agent.start()

if __name__ == "__main__":
    main()
