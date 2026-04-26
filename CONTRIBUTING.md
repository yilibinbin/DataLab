# Contributing to DataLab / 参与贡献

> 中文 + English. Pull requests welcome — 欢迎提交贡献。

## 🇨🇳 中文

### 报告问题

数值类问题(拟合不收敛、外推结果异常、LaTeX 输出 NaN 等)请附带:

1. **输入文件**(原始 `.txt` / `.csv`,或粘贴示意数据)
2. **复现步骤**(模式 / 公式 / 精度 dps)
3. **观察到的输出 vs. 期望输出**
4. **平台 + DataLab 版本**(release tag 或 git SHA)

非数值问题(GUI 卡顿、LaTeX 引擎找不到、打包失败等)请附 `~/.datalab/logs/` 下相关日志。

### 开发环境搭建

```bash
git clone https://github.com/yilibinbin/DataLab.git
cd DataLab

# 桌面端
pip install -r gui_requirements.txt
pip install -r requirements-test.txt
QT_QPA_PLATFORM=offscreen pytest -q   # 770+ tests 全绿

# 或 web 端
pip install -r web_requirements.txt
python app_web/server.py
```

详细架构见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

### 提交流程

1. **Fork + 新分支**:`feat/xxx` / `fix/xxx` / `chore/xxx` / `docs/xxx`
2. **TDD**:先写失败测试,再实现,验收 `pytest` 全绿
3. **遵守跨切关注点**(详见 `docs/ARCHITECTURE.md`):
   - 用户可见字符串走 `_dual_msg(zh, en)` 双语
   - mpmath 调用包在 `precision_guard(dps)` 上下文里
   - 表达式解析必须经过 `datalab_latex/expression_engine.py` 白名单
4. **提交信息**:`<type>: <description>`(`feat`/`fix`/`refactor`/`docs`/`test`/`chore`/`perf`)
5. **PR 描述**包含 Summary + Test plan(参考已合并的 PR)

### 代码风格

- Python 3.11+,PEP 8,**类型注解必加**(strict mypy 在 `shared/` `fitting/` `extrapolation_methods/` `datalab_latex/` 已启用)
- 黑色 (`black`) 格式化,`ruff` lint
- 文件大小目标 200–400 行,800 行为硬上限

---

## 🇬🇧 English

### Filing issues

For numerical bugs (fits not converging, extrapolation diverging, NaN
in LaTeX output, etc.) include:

1. **Input file** (raw `.txt` / `.csv`, or pasted sample data)
2. **Reproduction steps** (mode / formula / precision `dps`)
3. **Observed output vs. expected output**
4. **Platform + DataLab version** (release tag or git SHA)

For non-numerical issues (GUI hangs, LaTeX engine not found, build failures)
attach the relevant log from `~/.datalab/logs/`.

### Development setup

```bash
git clone https://github.com/yilibinbin/DataLab.git
cd DataLab

# Desktop frontend
pip install -r gui_requirements.txt
pip install -r requirements-test.txt
QT_QPA_PLATFORM=offscreen pytest -q   # 770+ tests, all green

# Or web frontend
pip install -r web_requirements.txt
python app_web/server.py
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the architecture map.

### Submission flow

1. **Fork + branch**: `feat/xxx` / `fix/xxx` / `chore/xxx` / `docs/xxx`
2. **TDD**: write the failing test first, implement to make it pass,
   confirm `pytest` is green
3. **Honor cross-cutting conventions** (full list in `docs/ARCHITECTURE.md`):
   - User-facing strings go through `_dual_msg(zh, en)` (bilingual)
   - mpmath calls wrap in `precision_guard(dps)` context
   - Expression parsing must go through the
     `datalab_latex/expression_engine.py` whitelist (do NOT add a
     parallel parser)
4. **Commit message format**: `<type>: <description>`
   (`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf`)
5. **PR description**: include Summary + Test plan (model after merged PRs)

### Coding style

- Python 3.11+, PEP 8, **type annotations required** (strict mypy is
  enabled on `shared/`, `fitting/`, `extrapolation_methods/`,
  `datalab_latex/`)
- Format with `black`, lint with `ruff`
- Target file size 200–400 lines; 800 is the hard cap

### License

By contributing, you agree your contributions will be licensed under the
[MIT License](LICENSE) (the project's license).
