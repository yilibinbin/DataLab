# 开发说明：新增“统计平均”模式与本地 pix2tex 公式识别（支持图片 / 截图 / 手写）

> **重要提示 / Important notice**  
> 本文件为**历史开发笔记**（早期单文件 GUI 架构），已**不代表当前实现**：R3/R4 之后代码已拆分为 `app_desktop/` 多个 mixin 与 `datalab_latex/` 子模块。本文档中的方法名/参数名/示例可能已过时。  
> This file is a **historical development note** from the early single-file GUI era and **does not reflect the current architecture**. Method names, signatures, and examples here may be outdated.  
> 当前实现与入口请参考：`CODE_REVIEW_R4.md`、`CODE_REVIEW_R6.md`、以及框架文档 `docs/PROGRAM_FRAMEWORK.tex` / `docs/PROGRAM_FRAMEWORK.en.tex`。

> 说明：本文件是给代码助手直接使用的开发文档。  
> 已有工程：**PySide6 GUI + mpmath + 自定义外推/误差/拟合工具**。  
> 本文档在此基础上增加：
>
> 1. 新的计算模式：**统计平均**（算术平均 + 加权平均，基于 mpmath）

下面所有代码改动都假定工作文件是你的主 GUI 脚本（有 `ExtrapolationWindow` 的那个文件）。

---

## 一、增加“统计平均”计算模式

### 1.1 在模式下拉框中添加“统计平均”

在 `ExtrapolationWindow._build_left_panel` 中，找到模式选择：

```python
self.mode_combo = QComboBox()
self.mode_combo.addItem("外推", "extrapolation")
self.mode_combo.addItem("误差传递", "error")
self.mode_combo.addItem("拟合", "fitting")
self.mode_combo.currentIndexChanged.connect(self._on_mode_change)

修改为（新增一项）：

self.mode_combo = QComboBox()
self.mode_combo.addItem("外推", "extrapolation")
self.mode_combo.addItem("误差传递", "error")
self.mode_combo.addItem("拟合", "fitting")
self.mode_combo.addItem("统计平均", "statistics")  # 新增
self.mode_combo.currentIndexChanged.connect(self._on_mode_change)

1.2 新建统计设置面板 stats_box
仍在 _build_left_panel 中、拟合模块附近，加入一个新的 QGroupBox：
# --- Statistics box (new) ---
self.stats_box = QGroupBox("统计平均设置")
stats_layout = QFormLayout(self.stats_box)

# 用于统计的数值列（如 A/B/C）
self.stats_value_column_edit = QLineEdit("A")
stats_layout.addRow("数值列：", self.stats_value_column_edit)

# 可选的不确定度（σ）列，用于加权平均
self.stats_sigma_column_edit = QLineEdit("")
stats_layout.addRow("不确定度列（可选）：", self.stats_sigma_column_edit)

# 统计类型选择
self.stats_mode_combo = QComboBox()
self.stats_mode_combo.addItem("算术平均（样本）", "mean_sample")
self.stats_mode_combo.addItem("算术平均（总体）", "mean_population")
self.stats_mode_combo.addItem("加权平均（σ 加权）", "weighted_sigma")
stats_layout.addRow("统计类型：", self.stats_mode_combo)

self.left_layout.addWidget(self.stats_box)
self.stats_box.hide()  # 默认隐藏

1.3 更新 _on_mode_change，控制各面板显示

找到原来的 _on_mode_change，替换为：
def _on_mode_change(self):
    mode = self.mode_combo.currentData()
    if mode == "extrapolation":
        self.extrap_box.show()
        self.error_box.hide()
        self.fit_box.hide()
        self.stats_box.hide()
    elif mode == "error":
        self.extrap_box.hide()
        self.error_box.show()
        self.fit_box.hide()
        self.stats_box.hide()
    elif mode == "fitting":
        self.extrap_box.hide()
        self.error_box.hide()
        self.fit_box.show()
        self.stats_box.hide()
    elif mode == "statistics":
        self.extrap_box.hide()
        self.error_box.hide()
        self.fit_box.hide()
        self.stats_box.show()

1.4 新增 _run_statistics_mode 实现统计功能

在 ExtrapolationWindow 类中新增方法（可放在 _run_fitting_mode 附近）：
def _run_statistics_mode(self, generate_latex: bool, output_path: str):
    # 1. 读取数据：重用通用表格解析逻辑
    headers, rows = self._collect_fitting_dataset()
    if not rows:
        raise ValueError("没有可用于统计的数据。")

    value_col = self.stats_value_column_edit.text().strip()
    if not value_col:
        raise ValueError("请在统计设置中指定数值列。")

    values = self._column_series(headers, rows, value_col)
    sigma_col = self.stats_sigma_column_edit.text().strip()
    sigmas = self._column_series(headers, rows, sigma_col) if sigma_col else None

    # 2. 设置多精度
    precision = self._read_precision()
    self._set_fit_output_precision(precision)

    n = len(values)
    if n == 0:
        raise ValueError("统计列中没有数据。")

    stats_mode = self.stats_mode_combo.currentData()

    # 3. 根据模式计算
    if stats_mode in {"mean_sample", "mean_population"}:
        # 算术平均
        mean = mp.nsum(lambda i: values[i], range(n)) / n

        # 方差: 样本(N-1) 或 总体(N)
        if n > 1:
            denom = (n - 1) if stats_mode == "mean_sample" else n
            var = mp.nsum(lambda i: (values[i] - mean) ** 2, range(n)) / denom
            std = mp.sqrt(var)
        else:
            std = mp.mpf("0")

        # 均值标准误差（标准差 / sqrt(n)）
        if n > 1:
            std_mean = std / mp.sqrt(n)
        else:
            std_mean = std

        method_label = "算术平均（样本）" if stats_mode == "mean_sample" else "算术平均（总体）"

    elif stats_mode == "weighted_sigma":
        if sigmas is None:
            raise ValueError("加权平均需要指定不确定度列。")

        # w_i = 1 / sigma_i^2，只对 sigma_i > 0 的点加权
        weights: list[tuple[mp.mpf, mp.mpf]] = []
        for v, s in zip(values, sigmas):
            s_mp = mp.mpf(s)
            if s_mp <= 0:
                continue
            weights.append((mp.mpf(v), 1 / (s_mp * s_mp)))

        if not weights:
            raise ValueError("不确定度列无有效（>0）的数据，无法进行加权平均。")

        W = mp.nsum(lambda i: weights[i][1], range(len(weights)))
        mean = mp.nsum(lambda i: weights[i][0] * weights[i][1], range(len(weights))) / W
        # 加权平均的不确定度（标准误差）
        std_mean = mp.sqrt(1 / W)
        std = mp.mpf("nan")  # 可选：整体散布，如有需要可另行定义
        method_label = "加权平均（σ 加权）"

    else:
        raise ValueError("未知的统计模式。")

    # 4. 额外信息：最小值 / 最大值
    v_min = mp.nmin(values)
    v_max = mp.nmax(values)

    mean_str = self._format_uncertainty_value(mean, std_mean)

    lines = [
        "=== 统计平均结果 ===",
        f"模式: {method_label}",
        f"数据点数 n = {n}",
        f"列名: {value_col}",
        "",
        f"平均值 (带标准误差): {mean_str}",
        f"平均值 = {self._format_precision_value(mean)}",
        f"标准误差 σ_mean = {self._format_precision_value(std_mean)}",
    ]
    if not mp.isnan(std):
        lines.append(f"标准差 σ = {self._format_precision_value(std)}")
    lines.extend(
        [
            "",
            f"最小值 min = {self._format_precision_value(v_min)}",
            f"最大值 max = {self._format_precision_value(v_max)}",
        ]
    )

    self._set_result_text("\n".join(lines))
    self._append_log("统计平均计算完成。")

    # 5. 可选：输出一个简单 LaTeX 报告
    if generate_latex and output_path:
        self._write_statistics_latex(
            headers,
            rows,
            value_col,
            mean,
            std_mean,
            std,
            v_min,
            v_max,
            output_path,
            method_label,
        )

1.5 新增 _write_statistics_latex 输出简易统计报告
在类中新增：
def _write_statistics_latex(
    self,
    headers,
    rows,
    value_col: str,
    mean: mp.mpf,
    std_mean: mp.mpf,
    std: mp.mpf,
    v_min: mp.mpf,
    v_max: mp.mpf,
    output_path: str,
    method_label: str,
):
    tex_path = Path(output_path).expanduser()

    lines = [
        "\\documentclass{article}",
        "\\usepackage{booktabs}",
        "\\usepackage{siunitx}",
        "\\usepackage{geometry}",
        "\\geometry{margin=1in}",
        "\\begin{document}",
        "\\section*{Statistics Report}",
        f"模式: {self._latex_escape(method_label)}\\\\",
        f"数值列: {self._latex_escape(value_col)}\\\\",
        "",
    ]

    mean_latex = self._format_uncertainty_value(mean, std_mean, latex=True)

    lines.append("\\subsection*{统计量}")
    lines.append("\\begin{itemize}")
    lines.append(f"  \\item 平均值: {mean_latex}")
    lines.append(f"  \\item 最小值: {self._latex_escape(self._format_precision_value(v_min))}")
    lines.append(f"  \\item 最大值: {self._latex_escape(self._format_precision_value(v_max))}")
    if not mp.isnan(std):
        lines.append(f"  \\item 标准差: {self._latex_escape(self._format_precision_value(std))}")
    lines.append("\\end{itemize}")

    lines.append("\\end{document}")

    try:
        tex_path.write_text("\n".join(lines), encoding="utf-8")
        self._append_log(f"统计 LaTeX 已写入: {tex_path}")
    except OSError as exc:
        QMessageBox.warning(self, "写入失败", str(exc))

1.6 在 run_calculation 中接入“统计平均”分支

找到 run_calculation 中处理模式的逻辑，目前大致是：
mode = self.mode_combo.currentData()
if mode == "extrapolation":
    ...
elif mode == "error":
    ...
else:
    self._run_fitting_mode(generate_latex, output_path)
替换为：
mode = self.mode_combo.currentData()
if mode == "extrapolation":
    # 原外推逻辑...
    ...
elif mode == "error":
    # 原误差传递逻辑...
    ...
elif mode == "fitting":
    self._run_fitting_mode(generate_latex, output_path)
elif mode == "statistics":
    self._run_statistics_mode(generate_latex, output_path)
