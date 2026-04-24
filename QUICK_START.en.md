# DataLab Web - Quick Start Guide

中文版本：QUICK_START.md

## 🎉 Feature Overview

DataLab Web currently supports:

### ✅ Short-term features (Web docs)
- 📄 `/docs` route - online Markdown documentation
- 🔒 Safe rendering - HTML escaping to prevent XSS
- 📚 Doc pages - index, guide, roadmap, etc.

### ✅ Mid-term features (i18n + interactive help)
- 🌐 Chinese/English bilingual UI - one-click switch in the top bar
- 💾 Language persistence - saved via localStorage
- ❓ Interactive help - "?" button popups
- 📖 Single source of truth - unified `help_specs.json`

---

## 📦 Install Dependencies

### Option 1: Use a virtual environment (recommended)

```bash
# 1. Create a virtual environment
cd /path/to/DataLab
python3 -m venv venv

# 2. Activate the virtual environment
source venv/bin/activate

# 3. Install Web dependencies
pip install -r web_requirements.txt
```

### Option 2: Install with `--user`

```bash
pip install --user -r web_requirements.txt
```

### Option 3: Install with `--break-system-packages` (not recommended)

```bash
pip install --break-system-packages -r web_requirements.txt
```

---

## 🚀 Start the Server

### Development mode

```bash
# Ensure you are in the venv (if you use one)
source venv/bin/activate

# Start the server
python app_web/server.py

# Or configure via environment variables
export DATALAB_HOST=127.0.0.1
export DATALAB_PORT=8000
python app_web/server.py
```

### Access the app

Open your browser:
- Home: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs

---

## 🧪 Run Tests

To verify everything works:

```bash
# Install test deps (optional; needed for GUI/PDF related tests):
pip install -r requirements-test.txt

# Headless GUI tests are recommended with offscreen
QT_QPA_PLATFORM=offscreen pytest -q
```

---

## 🌐 Use the bilingual UI

1. **Switch language**
   - Click the language dropdown in the top-right corner
   - Choose "中文" or "English"
   - The page updates immediately

2. **Language preference is saved**
   - Stored in the browser automatically
   - Applied on the next visit

3. **Covered UI text**
   - Navbar (序列外推 / Extrapolation)
   - Buttons (运行 / Run)
   - Help tooltips (Chinese/English)

---

## ❓ Use Interactive Help

### Formula help (Extrapolation / Error propagation)

1. Locate the formula input box
2. Click the "?" button next to it
3. A popup shows the list of allowed functions
4. Content follows the current language setting

### Method help (Extrapolation methods)

1. Select a method (e.g., "幂律外推")
2. Click the "?" button next to the method selector
3. Read method description, parameters, and usage notes
4. Content follows the current language setting

---

## 📖 View Documentation

### Embedded Web docs (lightweight)

Visit http://127.0.0.1:8000/docs to read:
- Home (index)
- Guide (guide)
- Extrapolation (extrapolation)
- Error propagation (uncertainty)
- Fitting (fitting)
- Statistics (statistics)
- Deployment (deploy)
- FAQ (faq)
- Roadmap (roadmap)

---

## 🔧 Troubleshooting

### Problem 1: `mistune` is not installed

**Symptom**: `/docs` errors or renders raw `<pre>` text.

**Fix**:
```bash
pip install "mistune>=2.0"
```

### Problem 2: Language switch does not work

**Symptom**: Clicking the language dropdown does nothing.

**Fix**:
1. Check your browser console for JavaScript errors
2. Ensure `app_web/static/js/i18n.js` is loaded
3. Clear cache and retry

### Problem 3: Help popup does not show

**Symptom**: Clicking the "?" button does nothing.

**Fix**:
1. Check `shared/help_specs.json` exists
2. Check your browser console for API errors
3. Ensure `/api/help_specs` endpoint is reachable

---

## 📋 Feature Checklist

Run the following checklist to ensure core features work:

### Basic features
- [ ] Visit home page http://127.0.0.1:8000
- [ ] Extrapolation works
- [ ] Error propagation works
- [ ] Fitting works
- [ ] Statistics works

### Documentation
- [ ] Visit `/docs` and open the docs index
- [ ] Visit `/docs/guide` for the guide page
- [ ] Markdown renders correctly (headings, lists, code blocks)
- [ ] Navbar/footer contain doc links

### Bilingual UI
- [ ] Language dropdown exists in top-right
- [ ] Switch to English and navbar becomes English
- [ ] Refresh keeps language selection
- [ ] Switch back to Chinese and navbar returns to Chinese

### Interactive help
- [ ] Click formula "?" in Extrapolation; function list appears
- [ ] Click formula "?" in Error propagation; function list appears
- [ ] Switching language updates help content
- [ ] Help popup can be closed normally

---

## 🚀 Production Deployment

See the embedded Web docs:
- `/docs/deploy` - Deployment and configuration

Key steps:
1. Set `DATALAB_WEB_SECRET`
2. Use Gunicorn (not the Flask dev server)
3. Configure Nginx reverse proxy
4. Enable HTTPS
5. Configure a systemd service (Linux)

---

## 📞 Get Help

- Docs: http://127.0.0.1:8000/docs
- FAQ: http://127.0.0.1:8000/docs/faq
- Roadmap: http://127.0.0.1:8000/docs/roadmap

---

**Enjoy!**
