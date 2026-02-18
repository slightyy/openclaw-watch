# OpenClaw Watch

> 多设备 OpenClaw 运行状态集中监控系统

## 一、项目概述

本项目是一套**多设备 OpenClaw 运行状态集中监控系统**，服务端部署在腾讯云 VPS 的 Docker 中，通过 Docker Compose 一键运行。被监控设备分布在全球各地外网环境，不在同一内网，通过轻量 Agent 定时向服务端上报数据。管理员通过浏览器访问 Web 面板，统一查看所有设备状态、资源、Token、日志。

## 二、部署环境要求

### 服务端运行环境
- 腾讯云 VPS（Linux x86_64）
- 必须使用 Docker + Docker Compose 部署
- 端口：
  - **38888**：Web 管理界面（外网可访问）
  - **38889**：API 数据上报端口（外网可访问）
- 数据库：SQLite（文件存储，数据持久化）
- 架构：Python FastAPI 后端 + HTML/JS 前端 + ECharts 图表

### 被监控端
- Windows / macOS / Linux 通用
- 运行一个轻量 Python Agent
- 每 30 秒向 VPS 服务器上报一次数据

## 三、完整功能清单

| 功能 | 说明 |
|------|------|
| 设备管理 | 支持添加、删除、查看多台外网 OpenClaw 设备，每台设备拥有唯一 API Key 鉴权 |
| 在线状态监控 | 自动判断设备在线 / 离线，超时未上报自动标记离线 |
| OpenClaw 运行状态 | 监控 OpenClaw 是否启动、版本 |
| CPU 监控 | 实时 CPU 使用率 |
| 内存监控 | 总内存、已用内存、使用率 |
| 磁盘监控 | 磁盘总容量、已用、使用率 |
| 网络监控 | 网络上传 / 下载速度 |
| Token 统计 | 今日 Token、昨日 Token、累计 Token、按设备统计 |
| 错误日志收集 | 自动收集各设备 OpenClaw 错误、崩溃、异常日志 |
| 日志展示 | 按设备、时间倒序展示 |
| 趋势图 | CPU / 内存 / 磁盘 趋势图 |
| 设备概览仪表盘 | 一页展示所有设备在线状态、资源占用、Token、最新错误 |

## 四、技术架构

| 组件 | 技术 |
|------|------|
| 后端 | Python FastAPI |
| 数据库 | SQLite |
| 前端 | HTML + JavaScript + ECharts |
| Agent | Python 跨平台脚本 |
| 部署 | Docker + Docker Compose |
| 通信 | HTTP API + Header 携带 API Key 鉴权 |
| 上报间隔 | 30 秒 |

## 五、端口规划

| 端口 | 用途 |
|------|------|
| 38888 | Web 管理页面（浏览器访问） |
| 38889 | Agent 数据上报 API（给外网设备用） |

## 六、快速开始

### 1. 服务端部署（腾讯云 VPS）

```bash
# 安装 Docker（如果没有）
curl -fsSL https://get.docker.com | sh
systemctl start docker
systemctl enable docker

# 克隆项目
git clone https://github.com/slightyy/openclaw-watch.git
cd openclaw-watch

# 启动服务
docker-compose up -d --build
```

访问：`http://你的VPS IP:38888`

### 2. 添加设备

1. 打开 Web 界面
2. 点击"添加设备"
3. 填写设备名称和类型
4. 保存后会生成 API Key

### 3. 被监控设备安装 Agent

```bash
# 下载 Agent
git clone https://github.com/slightyy/openclaw-watch.git
cd openclaw-watch/agent

# 编辑配置
nano openclaw_watch.env
```

修改配置：
```
NAS_URL=http://你的VPS IP:38889
API_KEY=你生成的API Key
REPORT_INTERVAL=30
```

启动 Agent：
```bash
pip install -r requirements.txt
python agent.py
```

或者使用后台运行：
```bash
NAS_URL=http://你的VPS IP:38889 API_KEY=你的Key nohup python agent.py > agent.log 2>&1 &
```

## 七、目录结构

```
openclaw-watch/
├── docker-compose.yml     # Docker Compose 配置
├── server/                # 服务端
│   ├── Dockerfile
│   ├── main.py           # FastAPI 主程序
│   └── requirements.txt
├── agent/                 # 被监控端 Agent
│   ├── agent.py           # Agent 主程序
│   ├── requirements.txt
│   ├── install.sh         # Linux 安装脚本
│   └── install.bat        # Windows 安装脚本
└── README.md
```

## 八、更新日志

### v1.1 (2026-02-18)
- 新增网络监控（上传/下载速度）
- 新增昨日Token统计
- 新增ECharts趋势图
- 优化设备卡片展示
- 端口调整为 38888/38889

### v1.0 (2026-02-17)
- 初始版本
- 设备监控、状态上报、Token统计

## 九、注意事项

1. **安全**：API Key 是设备身份标识，请妥善保管
2. **防火墙**：确保腾讯云安全组开放 38888 和 38889 端口
3. **Token 计算**：当前按 $1/1M tokens 估算费用，可根据实际模型价格修改
