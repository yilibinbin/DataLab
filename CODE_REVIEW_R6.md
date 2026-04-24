# DataLab 第六轮代码审阅报告

**审阅日期**: 2026-03-05  
**审阅范围**: 基于第五轮审阅建议修改后的全部源代码 + **文档完整性** + **中英文一一对应审计**  
**对比基线**: `CODE_REVIEW_R5.md`（含 R5 追踪表）

---

## 零、R6 建议落实追踪表

| ID | 结论(Implemented/Partially/Deferred/Incorrect/Already) | 落地位置(文件/符号) | 说明(原因/风险/验证方式) |
|---|---|---|---|
| D6-1 | Implemented | `README.md` | 修正文档中对 `app_web/logic.py` 的过时引用为 `app_web/logic/` 包；验证：文档审阅 + `tests/test_docs_sanity.py` |
| D6-2 | Implemented | `README.md` | 移除不存在的 `IMPLEMENTATION_REPORT.md` 链接并替换为现有文档；验证：文档审阅 + `tests/test_docs_sanity.py` |
| D6-3 | Implemented | `README.md` | 修正打包步骤中 `cd data_draw` 为通用路径/当前目录；验证：文档审阅 + `tests/test_docs_sanity.py` |
| D6-4 | Implemented | `README.md` | 将过时的 “Tk window” 描述修正为 PySide6；验证：文档审阅 |
| D6-5 | Implemented | `QUICK_START.md` | 移除硬编码个人路径，改为通用 `<project-root>`/`/path/to/DataLab`；验证：文档审阅 |
| D6-6 | Implemented | `QUICK_START.en.md` | 为 `QUICK_START.md` 提供完整英文对照版本；验证：文件存在性 + `tests/test_docs_sanity.py` |
| D6-7 | Implemented | `Document.md` | 保留历史开发笔记，但在文件顶部增加醒目的双语“已过时/不代表当前实现”提示；验证：文档审阅 |
| D6-8 | Implemented | `docs/DATALAB_WEB_GUIDE.en.md` | 为 `docs/DATALAB_WEB_GUIDE.md` 提供完整英文对照版本；验证：文件存在性 + `tests/test_docs_sanity.py` |
| D6-9 | Implemented | `docs/METHODS_THEORY.en.tex`，`docs/PROGRAM_FRAMEWORK.en.tex` | 为两份中文 LaTeX 理论文档提供英文对照版本（`article` + `pdflatex` 可编译）；验证：`tests/test_theory_docs_compile.py` |
| B6-1 | Implemented | `app_desktop/window.py:browse_*` | `QFileDialog` 标题改为 `self._tr(zh,en)`，保证中英文一致；验证：源码审阅 + `tests/test_qfiledialog_titles_bilingual.py` |
| B6-2 | Implemented | `app_desktop/window_latex_pdf_mixin.py:open_latex_file/_persist_latex_editor/_prompt_engine_selection` | 同上；验证：源码审阅 + `tests/test_qfiledialog_titles_bilingual.py` |
| C6-1 | Implemented | `app_desktop/fitting_latex_writer.py` | 增加模块 docstring，明确其为 Qt-free 的拟合 LaTeX 生成器；验证：代码审阅 |

**基线采样（改动前，2026-03-05）**：
- `QT_QPA_PLATFORM=offscreen pytest -q`：`151 passed`
- `pytest -q tests/test_latex_compile_e2e.py`：`1 passed`
- 使用 `/Users/fanghao/Downloads/data.txt` 生成外推 LaTeX（`use_dcolumn=False`, `precision=10`）：`varwidth=8.00in`，且 `tabular` 列规格包含 `S[table-format=1.10]`
- `pdflatex` 编译后 PDF 页宽约 `8.3321in`

**落地后复核（改动后，2026-03-05）**：
- `QT_QPA_PLATFORM=offscreen pytest -q`：`156 passed`
- `pytest -q tests/test_latex_compile_e2e.py`：`1 passed`
- 使用 `/Users/fanghao/Downloads/data.txt` 生成外推 LaTeX（`use_dcolumn=False`, `precision=10`）：`varwidth=8.00in`，且 `tabular` 列规格包含 `S[table-format=1.10]`
- `pdflatex` 编译后 PDF 页宽约 `8.3321in`

## 一、第五轮发现的修复状态

R5 共提出 **4 项发现**（全部极低严重性）。以下逐项验证：

| R5 ID | 描述 | 状态 | 验证结果 |
|-------|------|------|----------|
| C5-1 | `fitting_latex_writer.py:156` `x_sigma` 防御性转换 | ✅ Implemented | 新增 `try/except` 防御，仅当可转为 `mp.mpf` 且非零才走不确定度格式化；`test_fitting_latex_writer.py` 含 invalid sigma 用例 |
| C5-2 | facade 仅导出表格 API（设计意图确认） | ✅ Already | 无需修改 |
| T5-1 | 补充 dcolumn/batch/stat-sys 测试 | ✅ Implemented | `test_fitting_latex_writer.py` 已扩展 |
| T5-2 | 测试文件 `_r4` 后缀 | ✅ Implemented | 已统一去除：`test_fitting_latex_writer.py`、`test_latex_tables_common_unit.py`、`test_latex_tables_facade_exports.py`；文档引用同步更新 |

**测试**: 44 文件，156 通过。

---

## 二、文档完整性审计

### 2.1 根目录文档

| 文件 | 状态 | 问题 |
|------|------|------|
| `README.md` (143行) | ⚠️ 有过时内容 | 见 D6-1 ~ D6-4 |
| `QUICK_START.md` (227行) | ⚠️ 纯中文 + 硬编码路径 | 见 D6-5 ~ D6-6 |
| `Document.md` (273行) | ❌ **完全过时** | 见 D6-7 |
| `FITTING_REVIEW_UPDATED.md` | ℹ️ 拟合模块设计文档 | 内容仍有效，但未随模块拆分更新引用 |
| `PDF_PREVIEW_DELIVERY.md` / `_IMPLEMENTATION_GUIDE.md` | ℹ️ PDF 预览设计文档 | 内容仍有效 |

### 2.2 `docs/` 目录

| 子目录 | 中文 | 英文 | 对应覆盖 |
|--------|------|------|---------|
| `docs/desktop/` | 11 个 `.zh.md` | 11 个 `.en.md` | ✅ 完整配对 + `manifest.json` |
| `docs/web/` | 11 个 `.zh.md` + 11 个 stub `.md` | 11 个 `.en.md` | ✅ 完整配对 |
| `docs/TEST_MATRIX.md` | — | 英文 (64行) | ✅ 内容准确 |
| `docs/DATALAB_WEB_GUIDE.md` | 中文 (16KB) | 英文（`DATALAB_WEB_GUIDE.en.md`） | ✅ 已补齐对照（D6-8） |
| `docs/METHODS_THEORY.tex` | 中文 (14KB) | 英文（`METHODS_THEORY.en.tex`） | ✅ 已补齐对照（D6-9） |
| `docs/PROGRAM_FRAMEWORK.tex` | 中文 (15KB) | 英文（`PROGRAM_FRAMEWORK.en.tex`） | ✅ 已补齐对照（D6-9） |

---

## 三、中英文一一对应审计

### 3.1 QFileDialog 标题（❌ 仅中文）

以下对话框标题仅使用硬编码中文，未走 `_tr()` 双语机制：

| 文件:行 | 当前标题 | 建议 |
|---------|---------|------|
| `window.py:351` | `"选择数据文件"` | `self._tr("选择数据文件", "Select Data File")` |
| `window.py:356` | `"保存 LaTeX"` | `self._tr("保存 LaTeX", "Save LaTeX")` |
| `window.py:361` | `"选择常数文件"` | `self._tr("选择常数文件", "Select Constants File")` |
| `window_latex_pdf_mixin.py:29` | `"选择 LaTeX 文件"` | `self._tr("选择 LaTeX 文件", "Select LaTeX File")` |
| `window_latex_pdf_mixin.py:172` | `"保存 LaTeX 文件"` | `self._tr("保存 LaTeX 文件", "Save LaTeX File")` |
| `window_latex_pdf_mixin.py:430` | `f"选择 {engine} 可执行文件"` | `self._tr(f"选择 {engine} 可执行文件", f"Select {engine} Executable")` |

### 3.2 QMessageBox 标题/内容（✅ 大部分已双语）

`QMessageBox.warning` / `.information` 调用已普遍使用 `self._tr("中文", "English")`，验证以下均已正确：
- `window_images_mixin.py:118` — `_tr("导出失败", "Export Failed")` ✅
- `window_data_mixin.py:205` — `_tr("读取失败", "Load failed")` ✅
- `window_extrapolation_mixin.py:556` — `_tr("警告", "Warning")` ✅
- `window_fitting_mixin.py:1269,1277` — `_tr("参数错误", "Parameter error")` ✅
- `window_latex_pdf_mixin.py:447` — `_tr("提示", "Notice")` ✅

### 3.3 `docs/desktop/` & `docs/web/` 内容对应性

每个主题均有 `.zh.md` / `.en.md` 配对，覆盖 11 个话题：index, guide, extrapolation, uncertainty, fitting, statistics, export, deploy, faq, roadmap, theory。✅ 完整。

---

## 四、新发现

### 4.1 文档类（重点）

| ID | 文件 | 问题 | 严重性 | 建议 |
|----|------|------|--------|------|
| D6-1 | `README.md:100` | 写 `app_web/logic.py`，实际已拆为 `app_web/logic/` 包 | 中 | 改为 `app_web/logic/` |
| D6-2 | `README.md:50` | 链接 `IMPLEMENTATION_REPORT.md`，该文件不存在 | 中 | 移除链接或创建对应文件 |
| D6-3 | `README.md:114,128` | `cd data_draw`，当前目录名为 `DataLab` | 中 | 改为 `cd DataLab` |
| D6-4 | `README.md:136` | 提到 "Tk window can use the same icon at runtime"，实际已迁移到 PySide6 | 低 | 改为 "the PySide6 window can use the same icon" |
| D6-5 | `QUICK_START.md:26` | 硬编码用户路径 `/Users/fanghao/Documents/Code/...` | 中 | 改为 `.` 或通用的 `<project-root>` 占位符 |
| D6-6 | `QUICK_START.md` | 全文纯中文，无英文版本 | 低 | 可选：添加英文 section 或创建 `QUICK_START_EN.md` |
| D6-7 | `Document.md` | **完全过时**：描述单文件 `ExtrapolationWindow._build_left_panel` 直接添加代码的旧架构，引用的 API（`_run_statistics_mode`、`_write_statistics_latex` 方法签名）与当前实现不符；代码示例使用旧的 `mean_sample`/`mean_population` 模式名（当前为 `mean` + `stats_sample_checkbox`） | 中 | 建议：(1) 标注为"历史开发笔记，不代表当前实现" 或 (2) 删除/归档 |
| D6-8 | `docs/DATALAB_WEB_GUIDE.md` | 仅中文，无英文版 | 低 | 可选：提供英文摘要或创建 `.en.md` 对照 |
| D6-9 | `docs/METHODS_THEORY.tex` / `PROGRAM_FRAMEWORK.tex` | 仅中文，无英文版 | 低 | LaTeX 理论文档以中文为主合理；可考虑添加英文摘要但优先级极低 |

### 4.2 代码双语类

| ID | 文件:行 | 问题 | 严重性 | 建议 |
|----|---------|------|--------|------|
| B6-1 | `window.py:351,356,361` | QFileDialog 标题仅中文 | 低 | 改为 `self._tr()` 调用（见上方 §3.1 详表） |
| B6-2 | `window_latex_pdf_mixin.py:29,172,430` | QFileDialog 标题仅中文 | 低 | 同上 |

### 4.3 代码细节

| ID | 文件 | 问题 | 严重性 | 建议 |
|----|------|------|--------|------|
| C6-1 | `fitting_latex_writer.py` | 无模块 docstring | 极低 | 可添加一行说明：Qt-free fitting LaTeX table generator |

---

## 五、量化指标

### 5.1 演进总览

| 指标 | R1 | R2 | R3 | R4 | R5 | R6 |
|------|----|----|----|----|-----|-----|
| GUI 模块数 | 1 | 7 | 7 | 15 | 16 | **16** |
| LaTeX 模块数 | 1 | 4 | 4 | 8 | 8 | **8** |
| 测试文件 | 14 | 26 | 38 | 38 | 41 | **44** |
| 测试通过 | ~30 | ~60 | ~85 | 126 | 148→151 | **156** |
| 最大单文件 | 8531行 | 386KB | 5961行 | 2027行 | 1860行 | **1860行** |

### 5.2 发现数趋势

| 轮次 | 新增发现 | 严重性 | 重点领域 |
|------|---------|--------|---------|
| R1 | 15 | 中3/低12 | 架构/安全 |
| R2 | 15 | 低15 | 重复/测试 |
| R3 | 11 | 低11 | 文件拆分 |
| R4 | 7 | 低7 | DRY/测试 |
| R5 | 4 | 极低4 | 收敛确认 |
| R6 | **12** | **中4/低6/极低2** | **文档+双语** |

> R6 发现数回升是因为本轮首次将**文档**和**双语 UI 一致性**纳入审阅范围，此前五轮聚焦于代码架构和逻辑正确性。

---

## 六、质量评分

| 维度 | R1 | R2 | R3 | R4 | R5 | R6 |
|------|----|----|----|----|-----|-----|
| 架构 | ★★★☆☆ | ★★★★☆ | ★★★★½ | ★★★★★ | ★★★★★ | ★★★★★ |
| 安全性 | ★★★½☆ | ★★★★½ | ★★★★½ | ★★★★½ | ★★★★½ | ★★★★½ |
| 测试 | ★★★☆☆ | ★★★★☆ | ★★★★½ | ★★★★½ | ★★★★¾ | ★★★★¾ |
| 代码重复 | ★★★☆☆ | ★★★½☆ | ★★★★½ | ★★★★¾ | ★★★★★ | ★★★★★ |
| 国际化 | ★★★½☆ | ★★★★☆ | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★½ |
| **文档** | — | — | — | — | — | **★★★½☆** |
| **总体** | **4.0** | **4.5** | **4.75** | **4.85** | **4.90** | **4.85** |

> R6 **总体评分从 4.90 回调至 4.85**，反映了文档维度的首次纳入。代码质量本身保持 4.90 水准，但文档滞后将总分拉低。

---

## 七、总结

**第六轮审阅确认：R5 全部 4 项发现已落实。本轮首次纳入文档和双语 UI 审计。**

本轮新增 **12 项发现**：
- **文档类 9 项**（中 4 / 低 5）：`README.md` 有 4 处过时引用，`Document.md` 完全过时，`QUICK_START.md` 硬编码路径且纯中文
- **双语 UI 类 2 项**（低）：6 个 `QFileDialog` 标题仅中文
- **代码类 1 项**（极低）：`fitting_latex_writer.py` 缺模块 docstring

### 优先修复建议

1. **高优先**（中严重性，文档）：
   - 修正 `README.md` 中的 `logic.py` → `logic/`、`data_draw` → `DataLab`、移除 `IMPLEMENTATION_REPORT.md` 链接
   - 标注 `Document.md` 为"历史开发笔记"或归档
   - 移除 `QUICK_START.md` 中的硬编码路径

2. **中优先**（低严重性，双语）：
   - 将 6 个 `QFileDialog` 标题改为 `self._tr()` 调用

3. **可选**（低/极低）：
   - `QUICK_START.md` 英文版、`DATALAB_WEB_GUIDE.md` 英文摘要、模块 docstring

---

*审阅者: AI 代码审阅助手*  
*审阅方法: 全部源代码 + 全部文档逐文件审阅，含双语 UI 字符串一致性审计*
