# DataLab Web 使用与技术文档

English version: DATALAB_WEB_GUIDE.en.md

本文档分为两部分：
- **第一部分：用户使用指南** - 面向最终用户，介绍如何使用 DataLab Web 的各项功能
- **第二部分：技术与部署文档** - 面向开发者和运维人员，介绍系统架构、部署方式和配置选项

---

## 第一部分：用户使用指南

### 1. 工具概览

DataLab Web 是一个基于浏览器的高精度数值计算工具，提供以下四大功能模块：

#### 1.1 序列外推（Extrapolation）
- **用途**：对数值序列进行外推，获得极限值或趋势预测
- **支持方法**：
  - 幂律外推（三点法）
  - Richardson 序列加速
  - Shanks 变换 / Wynn ε 算法
  - Levin u-transform
  - 自定义公式外推
  - 默认三点公式

#### 1.2 误差传递（Error Propagation）
- **用途**：计算带不确定度数据通过公式后的误差传递
- **特性**：
  - 支持数值偏导计算
  - 自动合成不确定度
  - 支持常数与数据的联合传播

#### 1.3 拟合（Fitting）
- **用途**：对数据进行曲线拟合，获取最佳拟合参数
- **支持模型**：
  - 多项式拟合
  - 反幂级数拟合
  - Padé 近似
  - 预设模型库（对数、指数组合等）
  - 自定义模型

#### 1.4 统计平均（Statistics）
- **用途**：对带不确定度的数据进行加权或非加权统计平均
- **支持模式**：
  - 简单平均
  - 样本方差估计
  - 加权方差

---

### 2. 数据输入方式

#### 2.1 文本粘贴输入
1. 在数据输入框中直接粘贴数据
2. 首行为表头（列名），后续行为数据
3. 列之间用空格或制表符分隔

**示例**：
```
A B C
-0.750000   -0.702321   -0.680145
-0.500000   -0.476901   -0.461822
-0.250000   -0.235440   -0.228512
```

#### 2.2 文件上传输入
1. 勾选"使用文件输入"复选框
2. 点击"上传 UTF-8 文本文件"按钮
3. 选择 `.txt`、`.dat` 或 `.csv` 格式文件
4. 文件格式与文本粘贴相同（首行表头，后续行数据）

#### 2.3 不确定度表示格式

DataLab Web 支持两种不确定度表示方法：

**方法 1：括号记号** - `值(末位不确定度)[10的指数]`
```
1.2345(67)       # 表示 1.2345 ± 0.0067
1.2345(67)[-2]   # 表示 1.2345 ± 0.0067 × 10^-2
```

**方法 2：独立列** - 值和不确定度分两列
```
值       不确定度
1.2345   0.0067
2.3456   0.0089
```

---

### 3. 各模块使用说明

### 3.1 序列外推

#### 步骤：
1. **输入数据**：粘贴或上传多列数据
2. **选择外推方法**：
   - **幂律外推**：适用于 `f(x) = A*x^(-p) + C` 形式的序列
   - **Richardson 加速**：适用于渐近展开序列
   - **Shanks/Wynn**：通用序列加速算法
   - **Levin u-transform**：适用于震荡或缓慢收敛序列
   - **自定义公式**：使用表达式自定义外推规则
3. **设置参数**：
   - **参考列**：用于计算不确定度的参考列（列名或序号）
   - **多精度 mp.dps**：数值计算精度（留空使用默认值 16）
   - **结果不确定度有效位数**：控制结果显示精度
4. **生成输出**：
   - 点击"运行外推并生成 LaTeX"
   - 查看结果表格、LaTeX 代码、可选图表和 PDF

#### 公式语法（自定义外推）：
- 使用 `A, B, C` 或列名表示数据列
- 使用 `x1, x2, x3, ...` 作为列的别名
- 支持函数：`Sin[x]`, `Cos[x]`, `Log[x]`, `Exp[x]`, `Sqrt[x]`, `Abs[x]`
- 示例：`(C - B)^2/(B - A) + C`

---

### 3.2 误差传递

#### 步骤：
1. **输入数据**：使用括号记号输入带不确定度的数据
   ```
   E1 E2 E3
   1.0000(5)   0.8000(4)   0.7000(2)
   1.2000(5)   0.9500(4)   0.8200(3)
   ```
2. **输入公式**：在"误差传递公式"框中输入计算公式
   - 使用列名或 `x1, x2, x3` 别名
   - 函数使用 Mathematica 风格：`Sin[x1]`, `Log[ALPHA]`
3. **可选：添加常数**：
   - 勾选"启用常数"
   - 输入常数列表（每行一个常数）：
     ```
     ALPHA 7.2973525693(11)[-3]
     BETA 1.0000(5)
     ```
4. **生成输出**：
   - 点击"运行误差传递并生成 LaTeX"
   - 查看误差传递结果、不确定度贡献分解图

#### 公式示例：
```
x1*ALPHA + x2/x3               # 简单算术
Sin[x1]^2 + Cos[x1]^2          # 三角函数
Exp[-x1*ALPHA] * x2            # 指数与乘法
Log[x1/x2] + Sqrt[x3]          # 对数与平方根
```

---

### 3.3 拟合

#### 步骤：
1. **输入数据**：上传或粘贴 `x y` 格式数据
   - 可包含不确定度：`x y(σ)` 或 `x y σ`
   ```
   x y
   1.0  2.1(5)
   2.0  4.2(5)
   3.0  6.0(5)
   ```
2. **选择拟合模式**：
   - **多项式拟合**：指定阶数
   - **反幂级数**：指定幂次范围
   - **Padé 拟合**：指定分子/分母阶数
   - **幂律极限拟合**：使用 `A*x**(-p)+C` 模板
   - **自定义模型**：输入自定义拟合表达式
3. **设置选项**：
   - **加权拟合**：勾选后使用不确定度加权
   - **对数坐标**：选择 `log-x`, `log-y`, 或 `log-log`
4. **查看结果**：
   - 拟合参数及误差
   - 拟合质量指标（χ², AIC, BIC, R², RMSE）
   - 拟合曲线与残差图

---

### 3.4 统计平均

#### 步骤：
1. **输入数据**：输入单列数据（可带不确定度）
   ```
   A
   1152842742.723(12)
   1152842742.740(18)
   1152842742.727(14)
   ```
2. **选择统计模式**：
   - **简单平均**：算术平均
   - **样本方差估计**：勾选"使用样本标准差"
   - **加权方差**：勾选"使用加权方差"
3. **查看结果**：
   - 平均值 ± 标准误差
   - 最大值、最小值、标准差
   - 有效数据点数量

---

### 4. 输出说明

#### 4.1 结果表格
- **外推值/结果值**：计算得到的数值
- **不确定度**：误差或标准差
- **LaTeX 格式**：带括号记号的格式化输出

#### 4.2 格式控制
- **科学计数法**：勾选复选框可切换显示格式
- **保留位数**：调整数值显示的有效位数

#### 4.3 导出选项
- **CSV 下载**：点击"下载 CSV"导出表格数据
- **LaTeX 代码**：复制 LaTeX 文本框内容到论文
- **PDF 下载**：如果启用了 PDF 编译，可下载完整 PDF 文档

---

### 5. 常见问题

#### Q1: 为什么我的公式报错？
A: 请检查：
- 函数使用了 Mathematica 风格首字母大写：`Sin[x]` 而非 `sin(x)`
- 列名或常数名拼写正确
- 使用了支持的函数（Sin, Cos, Log, Exp, Sqrt, Abs）

#### Q2: 列名映射规则是什么？
A: 系统支持三种列引用方式：
- **列名**：直接使用表头中的列名
- **x1, x2, x3**：按列顺序的别名（x1 = 第一列，x2 = 第二列）
- **A, B, C**：外推模式下的特殊别名

#### Q3: 对数坐标拟合有什么限制？
A: 使用对数坐标时：
- `log-x` 模式要求所有 x > 0
- `log-y` 模式要求所有 y > 0
- `log-log` 模式要求所有 x, y > 0

#### Q4: 如何理解不确定度贡献图？
A: 不确定度贡献图显示各输入变量对总不确定度的贡献百分比，帮助识别主要误差来源。

#### Q5: 多精度计算何时需要？
A: 以下情况建议设置更高的 `mp.dps`：
- 幂律外推（默认 80 位）
- Richardson 或 Shanks 加速（默认 80 位）
- 数据本身有非常高的精度要求

---

## 第二部分：技术与部署文档

### 1. 系统架构

#### 1.1 技术栈
- **后端框架**：Flask（Python Web 框架）
- **数值计算**：mpmath（多精度浮点运算）
- **科学计算内核**：基于 `data_extrapolation_latex_latest.py` 的共享计算模块
- **前端**：原生 HTML + CSS + JavaScript（无外部前端框架）
- **LaTeX 引擎**：pdflatex / xelatex（用于 PDF 生成）

#### 1.2 架构特点
- **纯 Python 实现**：无需 Node.js 或其他运行时
- **模块化设计**：前后端分离，计算核心可独立使用
- **共享代码库**：Web 版与桌面版（Qt GUI）共用同一套科学计算代码
- **安全加固**：内置 CSRF 保护、输入验证、LaTeX 沙箱执行

---

### 2. 本地运行

#### 2.1 环境要求
- Python 3.8+
- 依赖包（见 `web_requirements.txt` 或 `gui_requirements.txt`）

#### 2.2 安装步骤

```bash
# 1. 克隆或下载项目
cd /path/to/data_extrapolation_source

# 2. 安装依赖
pip install -r web_requirements.txt

# 3. 运行服务器
python app_web/server.py
```

#### 2.3 访问应用
打开浏览器访问：`http://127.0.0.1:8000`

#### 2.4 环境变量（可选）
```bash
# 设置监听地址（默认 127.0.0.1）
export DATALAB_HOST=0.0.0.0

# 设置端口（默认 8000）
export DATALAB_PORT=5000

# 开启调试模式（仅开发环境！）
export DATALAB_DEBUG=1
```

---

### 3. 服务器部署

#### 3.1 生产环境部署方式

**推荐方式 1：使用 Gunicorn + Nginx**

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

**推荐方式 2：使用 systemd 服务**

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

---

### 4. 配置项与环境变量

#### 4.1 必需配置（生产环境）

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

#### 4.2 可选配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `DATALAB_HOST` | `127.0.0.1` | 监听地址（`0.0.0.0` 表示所有接口） |
| `DATALAB_PORT` | `8000` | 监听端口 |
| `PORT` | `8000` | 备用端口变量（兼容云平台） |
| `DATALAB_DEBUG` | `0` | 调试模式（`1` 开启，生产环境必须为 `0`） |

---

### 5. 安全建议

#### 5.1 密钥管理
- ✅ **DO**: 使用环境变量或密钥管理服务存储 `DATALAB_WEB_SECRET`
- ✅ **DO**: 定期轮换密钥
- ❌ **DON'T**: 将密钥硬编码到源代码
- ❌ **DON'T**: 将密钥提交到版本控制系统

#### 5.2 HTTPS 部署
生产环境必须使用 HTTPS：
```bash
# 使用 Let's Encrypt 免费证书
sudo certbot --nginx -d your-domain.com
```

#### 5.3 反向代理安全头
在 Nginx 配置中添加：
```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
```

#### 5.4 上传限制
系统已内置输入大小限制（默认 1MB），如需调整：
- 修改 `app_web/security.py` 中的 `MAX_TEXT_SIZE` 常量
- 同时调整 Nginx 的 `client_max_body_size`

#### 5.5 LaTeX 安全
- 系统使用沙箱执行 LaTeX 编译（`-no-shell-escape`）
- 限制编译时间（30 秒超时）
- 仅允许白名单引擎（`pdflatex`, `xelatex`, `lualatex`）

---

### 6. 日志与调试

#### 6.1 应用日志
Flask 默认输出到标准输出（stdout），使用 systemd 时可查看：
```bash
# 查看最新日志
sudo journalctl -u datalab-web -f

# 查看最近 100 行
sudo journalctl -u datalab-web -n 100
```

#### 6.2 调试模式
**仅开发环境使用！**
```bash
export DATALAB_DEBUG=1
python app_web/server.py
```

调试模式会：
- 启用详细错误页面
- 自动重载代码更改
- 输出详细日志

**警告**：生产环境绝不能开启调试模式，会泄露敏感信息！

---

### 7. 构建与升级

#### 7.1 更新依赖
```bash
# 更新 Python 包
pip install -r web_requirements.txt --upgrade

# 验证版本
pip list | grep Flask
pip list | grep mpmath
```

#### 7.2 数据库迁移
当前版本无数据库，所有计算均为无状态。

#### 7.3 热重载
使用 Gunicorn 进行平滑重启：
```bash
# 发送 HUP 信号重载配置
kill -HUP $(cat /var/run/gunicorn.pid)

# 或使用 systemd
sudo systemctl reload datalab-web
```

---

### 8. 性能优化

#### 8.1 Worker 数量
Gunicorn worker 数量建议：
- **CPU 密集型**（本应用属于此类）：`2 × CPU核心数 + 1`
- 示例：4 核 CPU → 9 workers

```bash
gunicorn -w 9 -b 127.0.0.1:8000 app_web.server:app
```

#### 8.2 缓存策略
当前版本无缓存，每次计算实时执行。如需加速：
- 考虑使用 Redis 缓存重复计算结果
- 实现计算任务队列（Celery）

#### 8.3 资源限制
使用 systemd 限制资源占用：
```ini
[Service]
MemoryMax=2G
CPUQuota=200%
```

---

### 9. 故障排查

#### 9.1 常见问题

**问题 1: LaTeX 编译失败**
- **原因**：系统未安装 LaTeX
- **解决**：
  ```bash
  # Ubuntu/Debian
  sudo apt-get install texlive texlive-latex-extra

  # macOS
  brew install --cask mactex
  ```

**问题 2: 端口被占用**
- **现象**：`Address already in use`
- **解决**：
  ```bash
  # 查找占用进程
  lsof -i :8000

  # 杀死进程或更换端口
  export DATALAB_PORT=8001
  ```

**问题 3: 权限错误**
- **现象**：`Permission denied`
- **解决**：确保运行用户有权限访问工作目录和日志目录

#### 9.2 性能问题
- **高精度计算慢**：正常现象，mp.dps 越高计算越慢
- **并发请求慢**：增加 worker 数量或使用异步 worker（`gunicorn -k gevent`）

---

### 10. API 端点参考（内部使用）

DataLab Web 提供以下 API 端点供前端调用：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/` | GET/POST | 序列外推页面 |
| `/error` | GET/POST | 误差传递页面 |
| `/fit` | GET/POST | 拟合页面 |
| `/stats` | GET/POST | 统计页面 |
| `/api/ui-specs` | GET | 获取 UI 动态配置 |
| `/api/function-help` | GET | 获取函数帮助文本 |
| `/api/method-help/<method>` | GET | 获取方法说明 |

---

### 11. 开发者指南

#### 11.1 项目结构
```
data_extrapolation_source/
├── app_web/                    # Web 应用目录
│   ├── server.py              # Flask 主程序
│   ├── security.py            # 安全模块（CSRF、输入验证）
│   ├── latex_security.py      # LaTeX 安全编译
│   ├── templates/             # Jinja2 模板
│   │   ├── base.html         # 基础模板
│   │   ├── index.html        # 外推页面
│   │   ├── error.html        # 误差传递页面
│   │   ├── fit.html          # 拟合页面
│   │   └── stats.html        # 统计页面
│   └── static/                # 静态资源
│       ├── style.css         # 样式表
│       └── ui_specs.js       # 前端逻辑
├── data_extrapolation_latex_latest.py  # 核心计算模块
├── extrapolation_methods/     # 外推算法
├── fitting/                   # 拟合模块
├── statistics_utils.py        # 统计工具
└── docs/                      # 文档目录
    └── DATALAB_WEB_GUIDE.md  # 本文档
```

#### 11.2 添加新功能
1. 修改对应的路由函数（`app_web/server.py`）
2. 更新模板（`app_web/templates/`）
3. 如需前端交互，修改 `ui_specs.js`
4. 添加测试用例

#### 11.3 测试
```bash
# 运行安全测试
python app_web/test_security.py

# 手动测试 CSRF 保护
# （启动服务器后访问任意页面，检查表单是否包含 csrf_token）
```

---

### 12. 许可证与贡献

本项目为科研工具，请遵守相关使用条款。如有问题或建议，请联系项目维护者。

---

**文档版本**：v1.0
**最后更新**：2025-12-13
**维护者**：DataLab Team
