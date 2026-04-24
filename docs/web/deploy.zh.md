# 部署与配置

本文档包含所有技术细节，包括 Python、Flask、环境变量等配置说明。

## 技术栈

- **后端框架**：Flask（Python Web 框架）
- **数值计算**：mpmath（多精度浮点运算）
- **前端**：原生 HTML + CSS + JavaScript
- **LaTeX 引擎**：pdflatex / xelatex

## 本地运行

### 环境要求
- Python 3.8+
- 依赖包（见 `web_requirements.txt`）

### 安装步骤

```bash
# 1. 克隆或下载项目
cd /path/to/data_extrapolation_source

# 2. 安装依赖
pip install -r web_requirements.txt

# 3. 运行服务器
python app_web/server.py
```

### 访问应用
打开浏览器访问：`http://127.0.0.1:8000`

### 环境变量（可选）

```bash
# 设置监听地址（默认 127.0.0.1）
export DATALAB_HOST=0.0.0.0

# 设置端口（默认 8000）
export DATALAB_PORT=5000

# 开启调试模式（仅开发环境！）
export DATALAB_DEBUG=1
```

## 服务器部署

### 推荐方式 1：Gunicorn + Nginx

> 注意：**Gunicorn 仅支持 Linux/macOS（POSIX）**。在原生 Windows 上会因为缺少 `fcntl` 而无法运行。

```bash
# 1. 安装 Gunicorn
pip install gunicorn

# 2. 启动 Gunicorn（4 个 worker）
gunicorn -w 4 -b 127.0.0.1:8000 app_web.server:app

# 3. 配置 Nginx 反向代理
# /etc/nginx/sites-available/datalab
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# 4. 重启 Nginx
sudo systemctl restart nginx
```

### 推荐方式 2：systemd 服务

创建 `/etc/systemd/system/datalab-web.service`：

```ini
[Unit]
Description=DataLab Web Application
After=network.target

[Service]
Type=notify
User=www-data
WorkingDirectory=/path/to/data_extrapolation_source
Environment="DATALAB_WEB_SECRET=your-secret-key-here"
Environment="DATALAB_HOST=127.0.0.1"
Environment="DATALAB_PORT=8000"
ExecStart=/usr/bin/gunicorn -w 4 -b 127.0.0.1:8000 app_web.server:app
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable datalab-web
sudo systemctl start datalab-web
```

### Windows（原生）推荐：Waitress

原生 Windows 无法使用 Gunicorn，请使用 Waitress：

```powershell
pip install waitress
waitress-serve --listen=192.168.85.1:8000 --threads=8 app_web.server:app
```

如需多进程 worker（CPU 密集型更合适），建议使用 **WSL2/Docker** 在 Linux 环境内运行 Gunicorn。

## 内置文档（/docs）

Web 端内置文档由路由 `/docs` 与 `/docs/<page>` 提供：

- 文档文件仅从 `docs/web/` 目录读取，并使用白名单页面映射（防止路径穿越）
- 文件命名规则：`docs/web/<page>.<lang>.md`，其中 `lang ∈ {zh,en}`
- 语言选择优先级：
  1) URL 参数 `?lang=zh` 或 `?lang=en`
  2) Cookie `datalab_lang`
  3) 默认 `zh`
- 若英文文件缺失：显示英文占位页，不会回退显示中文

## 配置项与环境变量

### 必需配置（生产环境）

**`DATALAB_WEB_SECRET`** - Flask 密钥
- **用途**：用于 session 加密和 CSRF 令牌生成
- **安全要求**：必须设置为随机且保密的字符串（至少 32 字符）
- **默认值**：`datalab-web-dev`（仅开发用，生产环境必须更改）

生成密钥示例：
```bash
# 方法 1：使用 Python
python -c "import secrets; print(secrets.token_hex(32))"

# 方法 2：使用 OpenSSL
openssl rand -hex 32

# 设置环境变量
export DATALAB_WEB_SECRET="your-generated-secret-key"
```

### 可选配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DATALAB_HOST` | `127.0.0.1` | 监听地址（`0.0.0.0` 表示所有接口） |
| `DATALAB_PORT` | `8000` | 监听端口 |
| `PORT` | `8000` | 备用端口变量（兼容云平台） |
| `DATALAB_DEBUG` | `0` | 调试模式（`1` 开启，生产环境必须为 `0`） |

## 安全建议

### 密钥管理
- ✅ 使用环境变量或密钥管理服务存储 `DATALAB_WEB_SECRET`
- ✅ 定期轮换密钥
- ❌ 将密钥硬编码到源代码
- ❌ 将密钥提交到版本控制系统

### HTTPS 部署
生产环境必须使用 HTTPS：
```bash
# 使用 Let's Encrypt 免费证书
sudo certbot --nginx -d your-domain.com
```

### 反向代理安全头
在 Nginx 配置中添加：
```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
```

### 上传限制
系统已内置输入大小限制（默认 1MB）。

### LaTeX 安全
- 使用沙箱执行 LaTeX 编译（`-no-shell-escape`）
- 限制编译时间（30 秒超时）
- 仅允许白名单引擎（`pdflatex`, `xelatex`, `lualatex`）

## 日志与调试

### 应用日志
Flask 默认输出到标准输出（stdout），使用 systemd 时可查看：
```bash
# 查看最新日志
sudo journalctl -u datalab-web -f

# 查看最近 100 行
sudo journalctl -u datalab-web -n 100
```

### 调试模式
**仅开发环境使用！**
```bash
export DATALAB_DEBUG=1
python app_web/server.py
```

**警告**：生产环境绝不能开启调试模式！

## 性能优化

### Worker 数量
Gunicorn worker 数量建议（CPU 密集型）：
- 公式：`2 × CPU核心数 + 1`
- 示例：4 核 CPU → 9 workers

```bash
gunicorn -w 9 -b 127.0.0.1:8000 app_web.server:app
```

### 资源限制
使用 systemd 限制资源占用：
```ini
[Service]
MemoryMax=2G
CPUQuota=200%
```

## 故障排查

### LaTeX 编译失败
- **原因**：系统未安装 LaTeX
- **解决**：
  ```bash
  # Ubuntu/Debian
  sudo apt-get install texlive texlive-latex-extra

  # macOS
  brew install --cask mactex
  ```

### 端口被占用
- **现象**：`Address already in use`
- **解决**：
  ```bash
  # 查找占用进程
  lsof -i :8000

  # 杀死进程或更换端口
  export DATALAB_PORT=8001
  ```

### 权限错误
- **现象**：`Permission denied`
- **解决**：确保运行用户有权限访问工作目录

## 构建与升级

### 更新依赖
```bash
# 更新 Python 包
pip install -r web_requirements.txt --upgrade

# 验证版本
pip list | grep Flask
pip list | grep mpmath
```

### 热重载
使用 Gunicorn 进行平滑重启：
```bash
# 发送 HUP 信号重载配置
kill -HUP $(cat /var/run/gunicorn.pid)

# 或使用 systemd
sudo systemctl reload datalab-web
```
