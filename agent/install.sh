#!/bin/bash
# OpenClaw Watch Agent 安装脚本 (Linux/macOS)

set -e

echo "========================================"
echo "OpenClaw Watch Agent 安装脚本"
echo "========================================"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 需要 Python 3"
    exit 1
fi

# 检查 pip
if ! command -v pip3 &> /dev/null; then
    echo "错误: 需要 pip3"
    exit 1
fi

# 获取 NAS 地址
read -p "请输入 NAS 服务地址 (例如 http://192.168.1.100:9000): " NAS_URL

# 获取 API Key
read -p "请输入设备 API Key: " API_KEY

if [ -z "$API_KEY" ]; then
    echo "错误: API Key 不能为空"
    exit 1
fi

# 安装依赖
echo "安装依赖..."
pip3 install -q requests psutil

# 创建配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/openclaw_watch.env"

cat > "$CONFIG_FILE" << EOF
# OpenClaw Watch Agent 配置
NAS_URL=$NAS_URL
API_KEY=$API_KEY
REPORT_INTERVAL=30
EOF

echo "配置文件已创建: $CONFIG_FILE"

# 创建启动脚本
START_SCRIPT="$SCRIPT_DIR/start_agent.sh"
cat > "$START_SCRIPT" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/openclaw_watch.env"
export NAS_URL
export API_KEY
export REPORT_INTERVAL
python3 "$SCRIPT_DIR/agent.py "$@
EOF

chmod +x "$START_SCRIPT"

# 创建 systemd 服务文件 (可选)
if command -v systemctl &> /dev/null; then
    read -p "是否创建 systemd 服务? (y/n): " CREATE_SERVICE
    if [ "$CREATE_SERVICE" = "y" ]; then
        SERVICE_FILE="/etc/systemd/system/openclaw-watch-agent.service"
        sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=OpenClaw Watch Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$START_SCRIPT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        echo "systemd 服务已创建: $SERVICE_FILE"
        echo "启用服务: sudo systemctl enable openclaw-watch-agent"
    fi
fi

echo ""
echo "========================================"
echo "安装完成!"
echo "========================================"
echo ""
echo "启动 Agent: $START_SCRIPT"
echo ""
echo "或者添加到 systemd:"
echo "  sudo systemctl enable openclaw-watch-agent"
echo "  sudo systemctl start openclaw-watch-agent"
echo ""
