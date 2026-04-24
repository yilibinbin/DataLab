# DataLab Web - 快速启动指南

English version: QUICK_START.en.md

## 🎉 功能总览

DataLab Web 现已支持：

### ✅ 短期功能（Web 文档）
- 📄 `/docs` 路由 - 在线 Markdown 文档
- 🔒 安全渲染 - HTML 转义防止 XSS
- 📚 文档页面 - index, guide, roadmap 等

### ✅ 中期功能（多语言 + 交互式帮助）
- 🌐 中/英双语支持 - 顶栏一键切换
- 💾 语言记忆 - localStorage 持久化
- ❓ 交互式帮助 - "?" 按钮弹窗说明
- 📖 帮助数据源 - 统一的 help_specs.json

---

## 📦 安装依赖

### 方法 1：使用虚拟环境（推荐）

```bash
# 1. 创建虚拟环境
cd /path/to/DataLab
python3 -m venv venv

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 安装 Web 应用依赖
pip install -r web_requirements.txt
```

### 方法 2：使用 --user 标志

```bash
pip install --user -r web_requirements.txt
```

### 方法 3：使用 --break-system-packages（不推荐）

```bash
pip install --break-system-packages -r web_requirements.txt
```

---

## 🚀 启动服务器

### 开发模式

```bash
# 确保在虚拟环境中（如果使用虚拟环境）
source venv/bin/activate

# 启动服务器
python app_web/server.py

# 或使用环境变量配置
export DATALAB_HOST=127.0.0.1
export DATALAB_PORT=8000
python app_web/server.py
```

### 访问应用

打开浏览器访问：
- 主页：http://127.0.0.1:8000
- 文档页面：http://127.0.0.1:8000/docs

---

## 🧪 运行测试

验证所有功能是否正常工作：

```bash
# 若需 GUI/PDF 相关测试，请先安装测试依赖：
pip install -r requirements-test.txt

# Headless GUI 测试建议设置 offscreen
QT_QPA_PLATFORM=offscreen pytest -q
```

---

## 🌐 使用多语言功能

1. **切换语言**：
   - 点击右上角的语言下拉框
   - 选择 "中文" 或 "English"
   - 页面立即切换语言

2. **语言设置保存**：
   - 语言偏好自动保存到浏览器
   - 下次访问自动应用

3. **支持的文案**：
   - 导航栏（序列外推/Extrapolation）
   - 按钮（运行/Run）
   - 帮助提示（中/英）

---

## ❓ 使用交互式帮助

### 公式帮助（外推/误差传递）

1. 找到公式输入框
2. 点击旁边的 "?" 按钮
3. 弹出窗口显示可用函数列表
4. 支持中/英语言切换

### 外推方法帮助

1. 选择外推方法（如"幂律外推"）
2. 点击方法选择器旁的 "?" 按钮
3. 查看方法说明、参数解释、适用场景
4. 内容跟随语言设置自动切换

---

## 📖 查看文档

### Web 内嵌文档（轻量）

访问 http://127.0.0.1:8000/docs，可查看：
- 首页（index）
- 使用指南（guide）
- 外推功能（extrapolation）
- 误差传递（uncertainty）
- 拟合功能（fitting）
- 统计分析（statistics）
- 部署配置（deploy）
- 常见问题（faq）
- 开发路线图（roadmap）

---

## 🔧 故障排查

### 问题 1：mistune 未安装

**现象**：访问 `/docs` 报错或显示 `<pre>` 原始文本

**解决**：
```bash
pip install "mistune>=2.0"
```

### 问题 2：语言切换不生效

**现象**：点击语言下拉框无反应

**解决**：
1. 检查浏览器控制台是否有 JavaScript 错误
2. 确认 `app_web/static/js/i18n.js` 已加载
3. 清除浏览器缓存后重试

### 问题 3：帮助弹窗不显示

**现象**：点击 "?" 按钮无反应

**解决**：
1. 检查 `shared/help_specs.json` 是否存在
2. 检查浏览器控制台是否有 API 错误
3. 确认 `/api/help_specs` 端点可访问

---

## 📋 功能检查清单

运行以下检查确保所有功能正常：

### 基础功能
- [ ] 访问主页 http://127.0.0.1:8000
- [ ] 外推功能正常工作
- [ ] 误差传递功能正常工作
- [ ] 拟合功能正常工作
- [ ] 统计功能正常工作

### 文档功能
- [ ] 访问 `/docs` 查看文档首页
- [ ] 访问 `/docs/guide` 查看使用指南
- [ ] Markdown 渲染正确（有标题、列表、代码块）
- [ ] 顶栏/页脚有文档链接

### 多语言功能
- [ ] 右上角有语言切换下拉框
- [ ] 切换到 English，导航栏变为英文
- [ ] 刷新页面，语言设置被保持
- [ ] 切换回中文，导航栏恢复中文

### 交互式帮助
- [ ] 外推页面点击公式 "?" 按钮，弹出函数帮助
- [ ] 误差传递页面点击公式 "?" 按钮，弹出函数帮助
- [ ] 切换语言后，帮助内容跟随切换
- [ ] 帮助弹窗可以正常关闭

---

## 🚀 生产环境部署

详细部署说明请参考：
- `/docs/deploy` - Web 内嵌文档

关键步骤：
1. 设置 `DATALAB_WEB_SECRET` 环境变量
2. 使用 Gunicorn 运行（而非 Flask 开发服务器）
3. 配置 Nginx 反向代理
4. 启用 HTTPS
5. 配置 systemd 服务

---

## 📞 获取帮助

- 查看文档：http://127.0.0.1:8000/docs
- 查看 FAQ：http://127.0.0.1:8000/docs/faq
- 查看开发路线图：http://127.0.0.1:8000/docs/roadmap

---

**开始使用吧！🎉**
