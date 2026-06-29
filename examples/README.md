# DataLab 示例数据 / Example datasets

本目录包含 DataLab 主要分析模式的示例输入文件；`workspaces/` 子目录包含可直接打开的 `.datalab` 工作区模板。用户可在 GUI 中加载输入文件，也可打开工作区模板学习完整配置。

This directory ships sample input files for DataLab modules. The `workspaces/`
subdirectory contains `.datalab` templates with full configuration snapshots.
The `recipes/` subdirectory contains declarative analysis recipes that can
configure supported workflows from the current data table without executing code.

## 文件清单 / File list

| 文件 | 模式 | 说明 |
|------|------|------|
| `extrapolation_richardson.txt` | Extrapolation | Richardson 三点序列加速:用 3 个不同精度的近似值外推到 ∞ |
| `fitting_powerlaw.txt` | Fitting | 幂律拟合:y ≈ A·x^p + C 含测量不确定度 |
| `error_propagation.txt` | Error Propagation | 双变量乘积公式 `V1 * V2` 的误差传递 |
| `statistics_weighted.txt` | Statistics | 加权平均:多次测量同一物理量,带各自的统计 σ |
| `constants.txt` | (Common) | 常数文件:供误差传递公式引用,如 ALPHA、G |
| `workspaces/statistics-matrix.datalab` | Statistics | 协方差/相关矩阵模板，展示三列 listwise 矩阵计算、LaTeX 和热图输出 |
| `workspaces/statistics-grouped.datalab` | Statistics | 分组统计模板，展示按文本分组对两列数据执行加权均值统计 |
| `workspaces/*.datalab` | Workspace templates | 只读模板，覆盖外推、误差传递、拟合、统计、求根与量子亏损示例 |
| `recipes/statistics-mean-basic.json` | Statistics recipe | 声明式配置单列统计平均，可绑定到 `statistics.datalab` 的 `Value` 列 |
| `recipes/error-product-basic.json` | Error recipe | 声明式配置 `V1 * V2` 误差传递，可绑定到 `error-propagation.datalab` |
| `recipes/fitting-custom-powerlaw.json` | Fitting recipe | 声明式配置 `A + B*x^(-C)` 加权自定义拟合，可绑定到 `fitting.datalab` |
| `recipes/root-batch-quadratic.json` | Root solving recipe | 声明式配置 `x^2 - A = 0` 批量求根，可绑定到 `root-batch-quadratic.datalab` |

新增的 `workspaces/error-propagation-units.datalab` 展示误差传递的单位标注：
默认使用仅显示模式，保证无 `pint` 环境也能直接运行；安装 `pint` 后可切换到
验证表达式模式，检查 `Distance / Time` 的输出单位 `m/s`。

## 输入格式速查 / Format crib sheet

- **数据文件**:**首行**直接写表头(空格 / Tab 分隔的列名),
  从第二行开始每行一条数据。**不要在数据文件首插入注释或空行**
  — 解析器以第一行为 header,前面的注释会被当列名解析。
- **单文件数据 + 常数**: 也可以使用 `[data]` 与 `[constants]`
  分段，把数据和常数放在同一个文本框或文件里。可见常数表/文本中的内容优先于文件中的
  `[constants]`，非空常数会自动使用，空白常数会被忽略。

  ```text
  [data]
  A B
  1.0(1) 2.0

  [constants]
  K = 3.2898419602500(36)[+9]
  ```
- **不确定度括号语法**:
  - `1.234(5)` ↔ 数值 = 1.234,σ = 0.005(末位)
  - `1.234(5)[-3]` ↔ 数值 = 1.234e-3,σ = 0.005e-3(科学计数法)
- 无不确定度的列直接写普通数字即可。
- **常数文件 (`constants.txt`)**:**支持** `#` 开头的注释行 + 空行
  (用 ``_process_constants_lines`` 解析,与数据文件不同)。

## Quick try in the GUI

1. 启动桌面 GUI(``python data_extrapolation_gui.py``)。
2. 在主界面顶部 mode 下拉框选择对应模式(如 "Extrapolation")。
3. 点 "打开数据文件",选择 ``examples/<对应文件>.txt``。
4. 需要常数时，可在左侧输入区的常数表/文本中填写，也可使用上面的 `[constants]`
   单文件格式；误差传递仍兼容单独的 ``examples/constants.txt`` 常数文件。
5. 也可通过 "打开示例工作区" 加载 ``examples/workspaces/*.datalab``。
6. 点 "运行" 即可看到结果 + LaTeX + PDF 预览。

## Usage tips

- For fitting examples, the σ on the y column controls the χ² weight;
  rows without an uncertainty fall back to unit weight.
- The constants file uses the same `ALPHA value` pair-per-line format
  the error-propagation form parses. For a single-file workflow, use `[data]`
  and `[constants]` sections in the same text/file input.
- The fitting and self-consistent quantum-defect workspaces are good places to
  inspect formula rendering. Enter formulas with DataLab/Mathematica-compatible
  syntax such as `Sin[x]`, `Sqrt[A]`, and `x^2`; the preview button renders the
  current expression as LaTeX-style math without changing the calculation.
- The unit-aware error-propagation workspace stores units in the workspace
  config and result snapshot provenance. Display-only mode changes labels only;
  active expression validation requires `pint` and fails closed when that
  optional dependency is unavailable.
- The covariance/correlation matrix workspace is Desktop-oriented. Select the
  Statistics mode, keep the covariance/correlation workflow, and enable plots
  to view the correlation heatmap.
- The grouped statistics workspace is Desktop-oriented. It stores all data
  directly, groups rows by the `Group` column, and runs weighted statistics for
  the `Signal` and `Reference` columns.
- Declarative recipes are JSON data, not plugins. The bundled recipes configure
  existing Statistics, Error Propagation, Fitting, and Root Solving workflows
  from the current data table; they do not execute Python, shell commands,
  imports, or network requests.
