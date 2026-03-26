#!/usr/bin/env bash
# =============================================================================
# Baby Time Machine — CentOS 7 一键部署脚本
# 环境：CentOS 7 + Nginx + Gunicorn + MySQL 8.0
# 使用：ssh root@<server-ip>  然后运行:
#       curl -fsSL https://raw.githubusercontent.com/Everyday888/Baby-Time-Machine/main/deploy/deploy.sh | bash
#   或者：
#       git clone https://github.com/Everyday888/Baby-Time-Machine.git /tmp/btm
#       bash /tmp/btm/deploy/deploy.sh
# =============================================================================
set -euo pipefail

# ── 可修改的常量 ──────────────────────────────────────────────────────────────
APP_DIR="/opt/baby-time-machine"
APP_USER="btm"
REPO_URL="https://github.com/Everyday888/Baby-Time-Machine.git"
GUNICORN_WORKERS=2
GUNICORN_PORT=5000
LOG_DIR="/var/log/baby-time-machine"
SERVICE_NAME="baby-time-machine"
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
divider() { echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

[[ $EUID -ne 0 ]] && error "请以 root 身份运行此脚本。"

divider
echo -e "  ${GREEN}🍼 宝贝时光机 — CentOS 7 部署脚本${NC}"
divider

# ══════════════════════════════════════════════════════════════════════════════
# 1. 收集配置（交互式）
# ══════════════════════════════════════════════════════════════════════════════
info "请输入部署配置（直接回车使用括号内的默认值）"
echo ""

read -rp "服务器公网 IP 或域名（用于生成邀请二维码，例如 58.87.70.226）: " SERVER_HOST
SERVER_HOST="${SERVER_HOST:-localhost}"

read -rp "MySQL root 密码（新安装时设置，已安装时输入现有密码）: " MYSQL_ROOT_PASS
[[ -z "$MYSQL_ROOT_PASS" ]] && error "MySQL root 密码不能为空。"

read -rp "应用 MySQL 用户名（默认 btm_user）: " MYSQL_USER
MYSQL_USER="${MYSQL_USER:-btm_user}"

read -rp "应用 MySQL 密码（默认随机生成）: " MYSQL_PASS
MYSQL_PASS="${MYSQL_PASS:-$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20)}"

read -rp "数据库名（默认 baby_time_machine）: " MYSQL_DB
MYSQL_DB="${MYSQL_DB:-baby_time_machine}"

# 生成随机 SECRET_KEY
DEFAULT_SECRET=$(tr -dc 'A-Za-z0-9!@#$%^&*' </dev/urandom | head -c 48)
read -rp "Flask SECRET_KEY（回车自动生成）: " SECRET_KEY
SECRET_KEY="${SECRET_KEY:-$DEFAULT_SECRET}"

echo ""
info "配置确认："
echo "  服务器地址   : $SERVER_HOST"
echo "  MySQL 用户   : $MYSQL_USER"
echo "  数据库名     : $MYSQL_DB"
echo "  应用目录     : $APP_DIR"
echo ""
read -rp "确认继续部署？(y/N) " CONFIRM
[[ "${CONFIRM,,}" != "y" ]] && error "已取消。"

# ══════════════════════════════════════════════════════════════════════════════
# 2. 安装系统依赖
# ══════════════════════════════════════════════════════════════════════════════
divider
info "安装系统基础依赖..."

yum install -y epel-release
yum install -y \
    git curl wget \
    gcc gcc-c++ make \
    openssl-devel bzip2-devel libffi-devel zlib-devel \
    readline-devel sqlite-devel \
    nginx \
    2>/dev/null

# ── Python 3.8（通过 SCL — Software Collections）──────────────────────────
info "安装 Python 3.8 (SCL rh-python38)..."
yum install -y centos-release-scl
yum install -y rh-python38 rh-python38-python-pip rh-python38-python-devel

PYTHON38="/opt/rh/rh-python38/root/usr/bin/python3.8"
[[ ! -f "$PYTHON38" ]] && error "Python 3.8 安装失败，请检查 SCL 源是否可用。"
info "Python 版本：$($PYTHON38 --version)"

# ── Node.js 20（用于安装 WebAwesome UI 组件）──────────────────────────────
if ! command -v node &>/dev/null; then
    info "安装 Node.js 20..."
    curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
    yum install -y nodejs
fi
info "Node.js 版本：$(node --version)"

# ══════════════════════════════════════════════════════════════════════════════
# 3. 安装 MySQL 8.0（若未安装）
# ══════════════════════════════════════════════════════════════════════════════
divider
if ! command -v mysql &>/dev/null; then
    info "安装 MySQL 8.0..."
    # 下载 MySQL 官方 repo（若超时可手动下载后 rpm -ivh）
    if ! rpm -qa | grep -q mysql80-community-release; then
        rpm --import https://repo.mysql.com/RPM-GPG-KEY-mysql-2023
        yum install -y https://dev.mysql.com/get/mysql80-community-release-el7-11.noarch.rpm
    fi
    # CentOS 7 需禁用自带的 mysql 模块
    yum module disable -y mysql 2>/dev/null || true
    yum install -y mysql-community-server
    systemctl enable --now mysqld

    # 从日志获取初始临时密码
    TEMP_PASS=$(grep 'temporary password' /var/log/mysqld.log 2>/dev/null | tail -1 | awk '{print $NF}')
    if [[ -n "$TEMP_PASS" ]]; then
        info "检测到 MySQL 临时密码，正在重置..."
        mysql --connect-expired-password -uroot -p"${TEMP_PASS}" \
            -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '${MYSQL_ROOT_PASS}';" 2>/dev/null
    fi
    info "MySQL 8.0 安装完成。"
else
    info "MySQL 已安装，跳过安装步骤。"
    systemctl is-active --quiet mysqld || systemctl start mysqld
fi

# ── 创建应用数据库和用户 ────────────────────────────────────────────────────
info "配置 MySQL 数据库和用户..."
mysql -uroot -p"${MYSQL_ROOT_PASS}" 2>/dev/null <<SQL
CREATE DATABASE IF NOT EXISTS \`${MYSQL_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${MYSQL_USER}'@'localhost' IDENTIFIED BY '${MYSQL_PASS}';
GRANT ALL PRIVILEGES ON \`${MYSQL_DB}\`.* TO '${MYSQL_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
info "数据库 '${MYSQL_DB}' 和用户 '${MYSQL_USER}' 已就绪。"

# ══════════════════════════════════════════════════════════════════════════════
# 4. 拉取/更新代码
# ══════════════════════════════════════════════════════════════════════════════
divider
info "部署应用代码到 ${APP_DIR}..."

if [[ -d "${APP_DIR}/.git" ]]; then
    info "检测到已有仓库，执行 git pull 更新..."
    git -C "${APP_DIR}" pull --ff-only origin main
else
    git clone "${REPO_URL}" "${APP_DIR}"
fi

# ── 创建应用运行用户 ────────────────────────────────────────────────────────
if ! id "${APP_USER}" &>/dev/null; then
    useradd -r -s /sbin/nologin -d "${APP_DIR}" "${APP_USER}"
    info "创建系统用户：${APP_USER}"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 5. 写入 .env 配置文件
# ══════════════════════════════════════════════════════════════════════════════
divider
info "生成 .env 配置文件..."
cat > "${APP_DIR}/.env" <<ENV
# Baby Time Machine — 生产环境配置
FLASK_APP=app
FLASK_ENV=production

SECRET_KEY=${SECRET_KEY}

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DB=${MYSQL_DB}
MYSQL_USER=${MYSQL_USER}
MYSQL_PASSWORD=${MYSQL_PASS}

# 公网访问地址（用于生成邀请二维码）
PUBLIC_BASE_URL=http://${SERVER_HOST}

# 邮件服务（可选，用于找回密码，留空则禁用邮件功能）
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
ENV
chmod 600 "${APP_DIR}/.env"
info ".env 已写入，权限已设为 600。"

# ══════════════════════════════════════════════════════════════════════════════
# 6. Python 虚拟环境 + pip 依赖
# ══════════════════════════════════════════════════════════════════════════════
divider
info "创建 Python 虚拟环境并安装依赖..."

# 使用 SCL Python 3.8 创建 venv
"${PYTHON38}" -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip --quiet
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt" --quiet
info "Python 依赖安装完成。"

# ══════════════════════════════════════════════════════════════════════════════
# 7. npm 安装 WebAwesome 前端组件
# ══════════════════════════════════════════════════════════════════════════════
divider
info "安装 Node.js 前端依赖（WebAwesome）..."
cd "${APP_DIR}"
npm install --production --quiet
info "node_modules 安装完成。"

# ══════════════════════════════════════════════════════════════════════════════
# 8. 初始化数据库表
# ══════════════════════════════════════════════════════════════════════════════
divider
info "初始化数据库表结构..."
cd "${APP_DIR}"
FLASK_APP=app "${APP_DIR}/.venv/bin/flask" init-db
info "数据库表创建成功。"

# ══════════════════════════════════════════════════════════════════════════════
# 9. 设置目录权限
# ══════════════════════════════════════════════════════════════════════════════
divider
info "设置文件权限..."
mkdir -p "${APP_DIR}/images" "${LOG_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${LOG_DIR}"
# nginx 需要读取静态文件
chmod o+x "${APP_DIR}"
info "权限设置完成。"

# ══════════════════════════════════════════════════════════════════════════════
# 10. Systemd 服务（Gunicorn）
# ══════════════════════════════════════════════════════════════════════════════
divider
info "注册 systemd 服务..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<SERVICE
[Unit]
Description=Baby Time Machine (Gunicorn)
After=network.target mysqld.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/gunicorn \\
    --workers ${GUNICORN_WORKERS} \\
    --bind 127.0.0.1:${GUNICORN_PORT} \\
    --timeout 120 \\
    --access-logfile ${LOG_DIR}/access.log \\
    --error-logfile ${LOG_DIR}/error.log \\
    app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
info "Gunicorn 服务已启动并设为开机自启。"

# ══════════════════════════════════════════════════════════════════════════════
# 11. Nginx 配置
# ══════════════════════════════════════════════════════════════════════════════
divider
info "配置 Nginx..."
cat > "/etc/nginx/conf.d/${SERVICE_NAME}.conf" <<NGINX
server {
    listen 80;
    server_name ${SERVER_HOST} _;

    client_max_body_size 20m;

    # 直接伺服静态文件（绕过 gunicorn，提升性能）
    location /static/ {
        alias ${APP_DIR}/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 上传的图片
    location /images/ {
        alias ${APP_DIR}/images/;
        expires 7d;
    }

    # WebAwesome UI 组件
    location /node_modules/ {
        alias ${APP_DIR}/node_modules/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 其余请求反代至 Gunicorn
    location / {
        proxy_pass         http://127.0.0.1:${GUNICORN_PORT};
        proxy_redirect     off;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
NGINX

# 允许 nginx 反代到本地端口（SELinux）
setsebool -P httpd_can_network_connect 1 2>/dev/null || true

# 检查 nginx 配置
nginx -t

# 移除 CentOS 7 自带的默认欢迎页
rm -f /etc/nginx/conf.d/default.conf 2>/dev/null || true

systemctl enable nginx
systemctl restart nginx
info "Nginx 已配置并重启。"

# ══════════════════════════════════════════════════════════════════════════════
# 12. 开放防火墙端口
# ══════════════════════════════════════════════════════════════════════════════
divider
if systemctl is-active --quiet firewalld; then
    info "开放防火墙 80 端口..."
    firewall-cmd --permanent --add-service=http
    firewall-cmd --reload
fi

# ══════════════════════════════════════════════════════════════════════════════
# 完成
# ══════════════════════════════════════════════════════════════════════════════
divider
echo ""
echo -e "  ${GREEN}✅  部署完成！${NC}"
echo ""
echo -e "  访问地址   : ${GREEN}http://${SERVER_HOST}${NC}"
echo ""
echo -e "  常用命令："
echo -e "    查看应用日志  : journalctl -u ${SERVICE_NAME} -f"
echo -e "    重启应用      : systemctl restart ${SERVICE_NAME}"
echo -e "    更新代码      : cd ${APP_DIR} && git pull && systemctl restart ${SERVICE_NAME}"
echo -e "    查看 Nginx 错误: tail -f /var/log/nginx/error.log"
echo ""

echo "=================================="
echo "  数据库信息（请妥善保存）"
echo "=================================="
echo "  MySQL Host     : localhost"
echo "  Database       : ${MYSQL_DB}"
echo "  User           : ${MYSQL_USER}"
echo "  Password       : ${MYSQL_PASS}"
echo "=================================="
echo ""
