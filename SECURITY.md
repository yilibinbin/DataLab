# Security Policy / 安全策略

## 🇨🇳 中文

### 支持的版本

| 版本 | 状态 |
|------|------|
| 2.0.x (latest) | ✅ 接受安全报告 |
| < 2.0 | ❌ 不再维护 |

### 报告漏洞

**请不要**通过公开 GitHub Issue 报告安全漏洞。

请通过以下渠道之一私下告知:

- **GitHub 私密报告**: 仓库 → Security → "Report a vulnerability"
  (推荐 — 自动加密 + 追踪)
- **邮件**: `wlx000610@gmail.com` (主题前缀 `[DataLab Security]`)

报告时请尽量包含:

1. 漏洞类型(命令注入 / 路径穿越 / 表达式逃逸 / 反序列化 等)
2. 复现步骤 + 最小化的输入数据
3. 受影响的版本或 commit SHA
4. 你认为的影响范围(本地 / 仅 GUI / 仅 Web 服务等)

### 响应时间

- **48 小时内**确认收到
- **7 天内**给出初步评估(是否构成漏洞 / 严重等级)
- **30 天内**修复并发布补丁(关键漏洞会更快)

### 已知风险面

DataLab 设计上的两类敏感入口,值得报告者重点关注:

1. **公式表达式解析** — `datalab_latex/expression_engine.py` 通过 AST
   白名单 + 节点 / 深度 cap 限制用户输入。如果你能在不绕白名单的
   情况下让它执行任意代码,这就是漏洞。
2. **Web 服务** — `app_web/server.py` 默认监听 `127.0.0.1`。如果你
   找到方式让它越过 CSRF / CSP / `DATALAB_WEB_SECRET` 校验,这就是漏洞。

### LaTeX 编译

DataLab 默认使用 [Tectonic](https://tectonic-typesetting.github.io/) ——
单一可执行文件,自动下载到 `~/.datalab/bin/`。我们**不会**在编译过程中
加载用户提供的 `\write18` 或 shell-escape 脚本。如果你发现绕过此限制的
方式,请按上述渠道报告。

---

## 🇬🇧 English

### Supported versions

| Version | Status |
|---------|--------|
| 2.0.x (latest) | ✅ Receiving security reports |
| < 2.0 | ❌ Unmaintained |

### Reporting a vulnerability

**Do not** open a public GitHub issue for security reports.

Use one of these private channels instead:

- **GitHub private report**: Repository → Security → "Report a vulnerability"
  (preferred — auto-encrypted + tracked)
- **Email**: `wlx000610@gmail.com` (subject prefix `[DataLab Security]`)

Please include:

1. Vulnerability class (command injection / path traversal / expression
   sandbox escape / deserialization, etc.)
2. Reproduction steps + minimized input
3. Affected version or commit SHA
4. Suspected impact scope (local / GUI only / web service only)

### Response time

- **Within 48 h** — acknowledgment of receipt
- **Within 7 days** — initial assessment (vulnerability or not, severity)
- **Within 30 days** — fix released (critical issues faster)

### Known attack surface

Two design-sensitive entry points worth focusing on:

1. **Formula expression parsing** — `datalab_latex/expression_engine.py`
   restricts user input via an AST whitelist + node / depth caps. If you
   can make it execute arbitrary code without subverting the whitelist,
   that's a vulnerability.
2. **Web service** — `app_web/server.py` binds `127.0.0.1` by default. If
   you find a way past the CSRF / CSP / `DATALAB_WEB_SECRET` checks,
   that's a vulnerability.

### LaTeX compilation

DataLab uses [Tectonic](https://tectonic-typesetting.github.io/) by
default — a single binary auto-downloaded to `~/.datalab/bin/`. We do
**not** enable `\write18` or shell-escape during compilation. If you find
a way around this restriction, report via the channels above.
