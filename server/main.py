"""
OpenClaw Watch Server - 主服务
"""
import os
import json
import time
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.future import select
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==================== 配置 ====================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////app/data/openclaw_watch.db")

# ==================== 数据库模型 ====================
Base = declarative_base()

class Device(Base):
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    device_type = Column(String(50), default="unknown")
    api_key = Column(String(100), unique=True, index=True, nullable=False)
    public_ip = Column(String(50))
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

class DeviceStatus(Base):
    __tablename__ = "device_status"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # OpenClaw 状态
    openclaw_version = Column(String(50))
    openclaw_status = Column(String(20))
    runtime = Column(String(50))
    model = Column(String(100))
    thinking = Column(String(20))
    
    # 系统资源
    cpu_percent = Column(Float)
    memory_percent = Column(Float)
    memory_total = Column(Float, default=0)
    memory_used = Column(Float, default=0)
    disk_percent = Column(Float)
    disk_total = Column(Float, default=0)
    disk_used = Column(Float, default=0)
    
    # 网络
    upload_speed = Column(Float, default=0)
    download_speed = Column(Float, default=0)
    
    # Token 使用
    context_tokens = Column(Integer)
    total_tokens = Column(Integer)

class ErrorLog(Base):
    __tablename__ = "error_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level = Column(String(20))
    message = Column(Text)
    source = Column(String(200))
    stack_trace = Column(Text)

# ==================== Pydantic 模型 ====================
class DeviceCreate(BaseModel):
    name: str
    device_type: str = "unknown"
    api_key: Optional[str] = None
    public_ip: Optional[str] = None
    notes: Optional[str] = None

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    public_ip: Optional[str] = None
    notes: Optional[str] = None

class DeviceResponse(BaseModel):
    id: int
    name: str
    device_type: str
    api_key: str
    public_ip: Optional[str]
    is_online: bool
    last_seen: Optional[datetime]
    created_at: datetime
    notes: Optional[str]
    
    class Config:
        from_attributes = True

class StatusReport(BaseModel):
    api_key: str
    openclaw_version: Optional[str] = None
    openclaw_status: Optional[str] = None
    runtime: Optional[str] = None
    model: Optional[str] = None
    thinking: Optional[str] = None
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    memory_total: Optional[float] = None
    memory_used: Optional[float] = None
    disk_percent: Optional[float] = None
    disk_total: Optional[float] = None
    disk_used: Optional[float] = None
    upload_speed: Optional[float] = None
    download_speed: Optional[float] = None
    public_ip: Optional[str] = None
    context_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

class ErrorReport(BaseModel):
    api_key: str
    level: str = "error"
    message: str
    source: Optional[str] = None
    stack_trace: Optional[str] = None

# ==================== 数据库初始化 ====================
engine = create_async_engine(DATABASE_URL, echo=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSession(engine) as session:
        yield session

# ==================== 应用生命周期 ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_device_online)
    scheduler.start()
    yield

app = FastAPI(title="OpenClaw Watch", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 辅助函数 ====================
async def check_device_online():
    """检查设备在线状态"""
    async with AsyncSession(engine) as session:
        result = await session.execute(select(Device))
        devices = result.scalars().all()
        now = datetime.utcnow()
        
        for device in devices:
            if device.last_seen:
                if (now - device.last_seen).total_seconds() > 300:
                    device.is_online = False
        
        await session.commit()

def verify_api_key(api_key: str, db: Session) -> Device:
    result = db.execute(select(Device).where(Device.api_key == api_key))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return device

# ==================== API 路由 ====================
@app.post("/api/devices", response_model=DeviceResponse)
async def create_device(device: DeviceCreate, db: AsyncSession = Depends(get_db)):
    import secrets
    api_key = device.api_key or secrets.token_hex(32)
    
    db_device = Device(
        name=device.name,
        device_type=device.device_type,
        api_key=api_key,
        public_ip=device.public_ip,
        notes=device.notes
    )
    db.add(db_device)
    await db.commit()
    await db.refresh(db_device)
    return db_device

@app.get("/api/devices", response_model=List[DeviceResponse])
async def list_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device))
    return result.scalars().all()

@app.get("/api/devices/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@app.put("/api/devices/{device_id}", response_model=DeviceResponse)
async def update_device(device_id: int, device: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.id == device_id))
    db_device = result.scalar_one_or_none()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device.name is not None:
        db_device.name = device.name
    if device.device_type is not None:
        db_device.device_type = device.device_type
    if device.public_ip is not None:
        db_device.public_ip = device.public_ip
    if device.notes is not None:
        db_device.notes = device.notes
    
    await db.commit()
    await db.refresh(db_device)
    return db_device

@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    await db.delete(device)
    await db.commit()
    return {"message": "Device deleted"}

# --- 状态上报 ---
@app.post("/api/report/status")
async def report_status(report: StatusReport, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.api_key == report.api_key))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    device.is_online = True
    device.last_seen = datetime.utcnow()
    if report.public_ip:
        device.public_ip = report.public_ip
    
    status = DeviceStatus(
        device_id=device.id,
        openclaw_version=report.openclaw_version,
        openclaw_status=report.openclaw_status,
        runtime=report.runtime,
        model=report.model,
        thinking=report.thinking,
        cpu_percent=report.cpu_percent or 0,
        memory_percent=report.memory_percent or 0,
        memory_total=report.memory_total or 0,
        memory_used=report.memory_used or 0,
        disk_percent=report.disk_percent or 0,
        disk_total=report.disk_total or 0,
        disk_used=report.disk_used or 0,
        upload_speed=report.upload_speed or 0,
        download_speed=report.download_speed or 0,
        context_tokens=report.context_tokens or 0,
        total_tokens=report.total_tokens or 0
    )
    db.add(status)
    await db.commit()
    
    return {"message": "Status received"}

@app.post("/api/report/error")
async def report_error(report: ErrorReport, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.api_key == report.api_key))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    error = ErrorLog(
        device_id=device.id,
        level=report.level,
        message=report.message,
        source=report.source,
        stack_trace=report.stack_trace
    )
    db.add(error)
    await db.commit()
    
    return {"message": "Error logged"}

# --- 监控数据查询 ---
@app.get("/api/devices/{device_id}/status")
async def get_device_status(device_id: int, hours: int = 24, db: AsyncSession = Depends(get_db)):
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(DeviceStatus)
        .where(DeviceStatus.device_id == device_id)
        .where(DeviceStatus.timestamp >= since)
        .order_by(DeviceStatus.timestamp.desc())
    )
    return result.scalars().all()

@app.get("/api/devices/{device_id}/errors")
async def get_device_errors(device_id: int, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ErrorLog)
        .where(ErrorLog.device_id == device_id)
        .order_by(ErrorLog.timestamp.desc())
        .limit(limit)
    )
    return result.scalars().all()

@app.get("/api/errors")
async def get_all_errors(
    device_id: Optional[int] = None,
    level: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    query = select(ErrorLog).order_by(ErrorLog.timestamp.desc()).limit(limit)
    
    if device_id:
        query = query.where(ErrorLog.device_id == device_id)
    if level:
        query = query.where(ErrorLog.level == level)
    
    result = await db.execute(query)
    return result.scalars().all()

# --- 统计 API ---
@app.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    # 设备数量
    devices_result = await db.execute(select(Device))
    devices = devices_result.scalars().all()
    total_devices = len(devices)
    online_devices = len([d for d in devices if d.is_online])
    
    # 获取所有状态数据
    all_result = await db.execute(select(DeviceStatus))
    all_status = list(all_result.scalars().all())
    
    # 最新 Token 总数
    latest_tokens = 0
    if all_status:
        latest_tokens = max((s.total_tokens or 0) for s in all_status)
    
    # 今日 Token
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await db.execute(
        select(DeviceStatus).where(DeviceStatus.timestamp >= today).order_by(DeviceStatus.timestamp.asc())
    )
    today_status = list(today_result.scalars().all())
    
    today_tokens = 0
    if len(today_status) >= 2:
        first_tokens = today_status[0].total_tokens or 0
        last_tokens = today_status[-1].total_tokens or 0
        today_tokens = max(0, last_tokens - first_tokens)
    elif len(today_status) == 1:
        today_tokens = today_status[0].total_tokens or 0
    
    # 昨日 Token
    yesterday = today - timedelta(days=1)
    yesterday_result = await db.execute(
        select(DeviceStatus).where(DeviceStatus.timestamp >= yesterday).where(DeviceStatus.timestamp < today).order_by(DeviceStatus.timestamp.asc())
    )
    yesterday_status = list(yesterday_result.scalars().all())
    
    yesterday_tokens = 0
    if len(yesterday_status) >= 2:
        first_tokens = yesterday_status[0].total_tokens or 0
        last_tokens = yesterday_status[-1].total_tokens or 0
        yesterday_tokens = max(0, last_tokens - first_tokens)
    
    # 错误数量
    errors_result = await db.execute(select(ErrorLog))
    errors = errors_result.scalars().all()
    total_errors = len(errors)
    
    # 设备列表（包含最新状态）
    device_list = []
    for device in devices:
        device_statuses = [s for s in all_status if s.device_id == device.id]
        latest = device_statuses[-1] if device_statuses else None
        
        device_list.append({
            "id": device.id,
            "name": device.name,
            "device_type": device.device_type,
            "public_ip": device.public_ip,
            "is_online": device.is_online,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "openclaw_version": latest.openclaw_version if latest else None,
            "cpu_percent": latest.cpu_percent if latest else 0,
            "memory_percent": latest.memory_percent if latest else 0,
            "memory_total": latest.memory_total if latest else 0,
            "memory_used": latest.memory_used if latest else 0,
            "disk_percent": latest.disk_percent if latest else 0,
            "disk_total": latest.disk_total if latest else 0,
            "disk_used": latest.disk_used if latest else 0,
            "upload_speed": latest.upload_speed if latest else 0,
            "download_speed": latest.download_speed if latest else 0,
            "total_tokens": latest.total_tokens if latest else 0,
        })
    
    return {
        "total_devices": total_devices,
        "online_devices": online_devices,
        "offline_devices": total_devices - online_devices,
        "today_tokens": today_tokens,
        "yesterday_tokens": yesterday_tokens,
        "total_tokens": latest_tokens,
        "total_errors": total_errors,
        "devices": device_list
    }

# --- 趋势图数据 ---
@app.get("/api/trends")
async def get_trends(hours: int = 24, db: AsyncSession = Depends(get_db)):
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(DeviceStatus)
        .where(DeviceStatus.timestamp >= since)
        .order_by(DeviceStatus.timestamp.asc())
    )
    statuses = list(result.scalars().all())
    
    # 按时间分组，每5分钟取一个点
    trends = defaultdict(lambda: {"cpu": [], "memory": [], "disk": []})
    
    for status in statuses:
        # 取整到5分钟
        ts = status.timestamp.replace(minute=(status.timestamp.minute // 5) * 5, second=0, microsecond=0)
        key = ts.isoformat()
        if status.cpu_percent:
            trends[key]["cpu"].append(status.cpu_percent)
        if status.memory_percent:
            trends[key]["memory"].append(status.memory_percent)
        if status.disk_percent:
            trends[key]["disk"].append(status.disk_percent)
    
    # 计算平均值
    result = []
    for ts, values in sorted(trends.items()):
        result.append({
            "time": ts,
            "cpu": sum(values["cpu"]) / len(values["cpu"]) if values["cpu"] else 0,
            "memory": sum(values["memory"]) / len(values["memory"]) if values["memory"] else 0,
            "disk": sum(values["disk"]) / len(values["disk"]) if values["disk"] else 0,
        })
    
    return result

# ==================== 前端静态文件 ====================
@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenClaw Watch - 监控面板</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px 24px; color: #fff; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 24px; }
        .header .time { font-size: 14px; opacity: 0.9; }
        
        .container { max-width: 1400px; margin: 0 auto; padding: 24px; }
        
        .stats { display: grid; grid-template-columns: repeat(6, 1fr); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: #fff; padding: 20px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.05); }
        .stat-card .label { color: #909399; font-size: 13px; margin-bottom: 8px; }
        .stat-card .value { font-size: 24px; font-weight: 600; color: #303133; }
        .stat-card .value.online { color: #67c23a; }
        .stat-card .value.offline { color: #f56c6c; }
        .stat-card .value.warning { color: #e6a23c; }
        
        .section { background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.05); margin-bottom: 24px; }
        .section-header { padding: 16px 20px; border-bottom: 1px solid #e4e7ed; display: flex; justify-content: space-between; align-items: center; }
        .section-header h2 { font-size: 16px; color: #303133; }
        
        .device-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 16px; padding: 20px; }
        .device-card { background: #fafafa; border-radius: 8px; padding: 16px; border: 1px solid #e4e7ed; }
        .device-card .header { background: none; padding: 0 0 12px 0; color: #303133; justify-content: space-between; }
        .device-card .name { font-weight: 600; font-size: 16px; }
        .device-card .status { padding: 4px 8px; border-radius: 4px; font-size: 12px; }
        .status-online { background: #e1f3d8; color: #67c23a; }
        .status-offline { background: #fde2e2; color: #f56c6c; }
        
        .device-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px; }
        .metric { text-align: center; }
        .metric .value { font-size: 18px; font-weight: 600; color: #303133; }
        .metric .label { font-size: 12px; color: #909399; }
        
        .chart-container { height: 300px; padding: 20px; }
        
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #e4e7ed; }
        th { background: #fafafa; color: #606266; font-weight: 500; font-size: 14px; }
        
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .btn-primary { background: #409eff; color: #fff; }
        .btn-danger { background: #f56c6c; color: #fff; }
        
        @media (max-width: 1200px) { .stats { grid-template-columns: repeat(3, 1fr); } }
        @media (max-width: 768px) { .stats { grid-template-columns: repeat(2, 1fr); } }
    </style>
</head>
<body>
    <div class="header">
        <h1>🕵️ OpenClaw Watch</h1>
        <div class="time" id="currentTime"></div>
    </div>
    
    <div class="container">
        <!-- 统计卡片 -->
        <div class="stats">
            <div class="stat-card">
                <div class="label">设备总数</div>
                <div class="value" id="totalDevices">-</div>
            </div>
            <div class="stat-card">
                <div class="label">在线设备</div>
                <div class="value online" id="onlineDevices">-</div>
            </div>
            <div class="stat-card">
                <div class="label">离线设备</div>
                <div class="value offline" id="offlineDevices">-</div>
            </div>
            <div class="stat-card">
                <div class="label">今日 Token</div>
                <div class="value" id="todayTokens">-</div>
            </div>
            <div class="stat-card">
                <div class="label">昨日 Token</div>
                <div class="value" id="yesterdayTokens">-</div>
            </div>
            <div class="stat-card">
                <div class="label">累计 Token</div>
                <div class="value" id="totalTokens">-</div>
            </div>
        </div>
        
        <!-- 资源使用 -->
        <div class="section">
            <div class="section-header">
                <h2>💻 资源使用</h2>
            </div>
            <div style="padding:20px;">
                <div style="margin-bottom:16px;">
                    <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                        <span>CPU</span>
                        <span id="cpuValue">0%</span>
                    </div>
                    <div style="background:#e4e7ed;border-radius:4px;height:20px;">
                        <div id="cpuBar" style="background:#409eff;height:100%;border-radius:4px;width:0%;transition:width 0.3s;"></div>
                    </div>
                </div>
                <div style="margin-bottom:16px;">
                    <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                        <span>内存</span>
                        <span id="memValue">0%</span>
                    </div>
                    <div style="background:#e4e7ed;border-radius:4px;height:20px;">
                        <div id="memBar" style="background:#67c23a;height:100%;border-radius:4px;width:0%;transition:width 0.3s;"></div>
                    </div>
                </div>
                <div>
                    <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                        <span>磁盘</span>
                        <span id="diskValue">0%</span>
                    </div>
                    <div style="background:#e4e7ed;border-radius:4px;height:20px;">
                        <div id="diskBar" style="background:#e6a23c;height:100%;border-radius:4px;width:0%;transition:width 0.3s;"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 设备列表 -->
        <div class="section">
            <div class="section-header">
                <h2>📱 设备列表</h2>
                <button class="btn btn-primary" onclick="showAddModal()">+ 添加设备</button>
            </div>
            <div class="device-grid" id="deviceList"></div>
        </div>
        
        <!-- 错误日志 -->
        <div class="section">
            <div class="section-header">
                <h2>⚠️ 最新错误</h2>
            </div>
            <table>
                <thead>
                    <tr><th>时间</th><th>设备</th><th>级别</th><th>消息</th></tr>
                </thead>
                <tbody id="errorList"></tbody>
            </table>
        </div>
    </div>
    
    <script>
        let stats = {};
        
        function formatBytes(bytes) {
            if (!bytes) return '0 B';
            if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + ' GB';
            if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
            if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return bytes + ' B';
        }
        
        function formatSpeed(bytes) {
            if (!bytes) return '0 KB/s';
            return (bytes / 1024).toFixed(1) + ' KB/s';
        }
        
        function formatTokens(num) {
            if (!num || num === 0) return '0';
            if (num >= 1000000) return (num / 1000000).toFixed(2) + 'M';
            if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
            return num.toString();
        }
        
        async function loadData() {
            try {
                stats = await fetch('/api/stats').then(r => r.json());
                const trends = await fetch('/api/trends?hours=24').then(r => r.json());
                const errors = await fetch('/api/errors?limit=10').then(r => r.json());
                
                updateStats();
                renderDevices();
                renderErrors(errors);
                renderChart(trends);
            } catch (e) {
                console.error('Load error:', e);
            }
        }
        
        function updateStats() {
            document.getElementById('totalDevices').textContent = stats.total_devices || 0;
            document.getElementById('onlineDevices').textContent = stats.online_devices || 0;
            document.getElementById('offlineDevices').textContent = stats.offline_devices || 0;
            document.getElementById('todayTokens').textContent = formatTokens(stats.today_tokens || 0);
            document.getElementById('yesterdayTokens').textContent = formatTokens(stats.yesterday_tokens || 0);
            document.getElementById('totalTokens').textContent = formatTokens(stats.total_tokens || 0);
            
            // 更新进度条 - 取第一个设备的资源使用
            if (stats.devices && stats.devices.length > 0) {
                const d = stats.devices[0];
                const cpu = d.cpu_percent || 0;
                const mem = d.memory_percent || 0;
                const disk = d.disk_percent || 0;
                
                document.getElementById('cpuValue').textContent = cpu.toFixed(1) + '%';
                document.getElementById('cpuBar').style.width = cpu + '%';
                document.getElementById('memValue').textContent = mem.toFixed(1) + '%';
                document.getElementById('memBar').style.width = mem + '%';
                document.getElementById('diskValue').textContent = disk.toFixed(1) + '%';
                document.getElementById('diskBar').style.width = disk + '%';
            }
        }
        
        function renderDevices() {
            const container = document.getElementById('deviceList');
            if (!stats.devices || stats.devices.length === 0) {
                container.innerHTML = '<p style="text-align:center;color:#909399;padding:40px;">暂无设备</p>';
                return;
            }
            
            container.innerHTML = stats.devices.map(d => `
                <div class="device-card">
                    <div class="header">
                        <span class="name">${d.name}</span>
                        <div>
                            <button class="btn btn-danger" style="padding:4px 8px;font-size:12px;margin-left:8px;" onclick="deleteDevice(${d.id})">删除</button>
                            <span class="status ${d.is_online ? 'status-online' : 'status-offline'}">${d.is_online ? '在线' : '离线'}</span>
                        </div>
                    </div>
                    <div style="font-size:12px;color:#909399;margin-top:4px;">IP: ${d.public_ip || '-'} | OpenClaw: ${d.openclaw_version || '-'}</div>
                    <div class="device-metrics">
                        <div class="metric">
                            <div class="value">${(d.cpu_percent || 0).toFixed(1)}%</div>
                            <div class="label">CPU</div>
                        </div>
                        <div class="metric">
                            <div class="value">${(d.memory_percent || 0).toFixed(1)}%</div>
                            <div class="label">内存</div>
                        </div>
                        <div class="metric">
                            <div class="value">${(d.disk_percent || 0).toFixed(1)}%</div>
                            <div class="label">磁盘</div>
                        </div>
                        <div class="metric">
                            <div class="value">${formatSpeed(d.upload_speed)}</div>
                            <div class="label">上传</div>
                        </div>
                        <div class="metric">
                            <div class="value">${formatSpeed(d.download_speed)}</div>
                            <div class="label">下载</div>
                        </div>
                        <div class="metric">
                            <div class="value">${formatTokens(d.total_tokens)}</div>
                            <div class="label">Token</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        function renderErrors(errors) {
            const tbody = document.getElementById('errorList');
            if (!errors || errors.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#909399;">暂无错误</td></tr>';
                return;
            }
            
            const deviceMap = {};
            if (stats.devices) {
                stats.devices.forEach(d => deviceMap[d.id] = d.name);
            }
            
            tbody.innerHTML = errors.map(e => `
                <tr>
                    <td>${new Date(e.timestamp).toLocaleString('zh-CN')}</td>
                    <td>${deviceMap[e.device_id] || '未知'}</td>
                    <td><span style="color:#f56c6c">${e.level}</span></td>
                    <td>${e.message || '-'}</td>
                </tr>
            `).join('');
        }
        
        function renderChart(data) {
            const chart = echarts.init(document.getElementById('trendChart'));
            const times = data.map(d => d.time.substring(11, 16));
            const cpu = data.map(d => d.cpu.toFixed(1));
            const memory = data.map(d => d.memory.toFixed(1));
            
            chart.setOption({
                tooltip: { trigger: 'axis' },
                legend: { data: ['CPU', '内存', '磁盘'] },
                grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
                xAxis: { type: 'category', data: times },
                yAxis: { type: 'value', max: 100, suffix: '%' },
                series: [
                    { name: 'CPU', type: 'line', data: cpu, smooth: true, itemStyle: {color: '#409eff'} },
                    { name: '内存', type: 'line', data: memory, smooth: true, itemStyle: {color: '#67c23a'} }
                ]
            });
        }
        
        function showAddModal() {
            const name = prompt('设备名称:');
            if (!name) return;
            
            const device_type = prompt('设备类型 (mac/linux/windows/vps/nas):') || 'vps';
            
            fetch('/api/devices', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, device_type})
            }).then(r => r.json()).then(d => {
                alert('设备添加成功！API Key: ' + d.api_key);
                loadData();
            });
        }
        
        function deleteDevice(id) {
            if (!confirm('确定要删除这个设备吗？')) return;
            
            fetch('/api/devices/' + id, {
                method: 'DELETE'
            }).then(r => {
                if (r.ok) {
                    alert('设备删除成功');
                    loadData();
                } else {
                    alert('删除失败');
                }
            });
        }
        
        function updateTime() {
            document.getElementById('currentTime').textContent = new Date().toLocaleString('zh-CN');
        }
        
        updateTime();
        setInterval(updateTime, 1000);
        loadData();
        setInterval(loadData, 30000);
    </script>
</body>
</html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
