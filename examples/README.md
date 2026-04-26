# DataLab 示例数据 / Example datasets

本目录包含 DataLab 四种主要分析模式的示例输入文件,用户可直接在 GUI 中
"打开数据文件"加载学习,或复制其中内容粘贴到手动输入表格。

This directory ships sample input files for the four main DataLab
analysis modes. Open them via "Load data file" in the desktop GUI or
paste the content into the manual-input table.

## 文件清单 / File list

| 文件 | 模式 | 说明 |
|------|------|------|
| `extrapolation_richardson.txt` | Extrapolation | Richardson 三点序列加速:用 3 个不同精度的近似值外推到 ∞ |
| `fitting_powerlaw.txt` | Fitting | 幂律拟合:y ≈ A·x^p + C 含测量不确定度 |
| `error_propagation.txt` | Error Propagation | 双变量公式 (x1+x2)/x1 的误差传递 |
| `statistics_weighted.txt` | Statistics | 加权平均:多次测量同一物理量,带各自的统计 σ |
| `constants.txt` | (Common) | 常数文件:供误差传递公式引用,如 ALPHA、G |

## 输入格式速查 / Format crib sheet

- **数据文件**:**首行**直接写表头(空格 / Tab 分隔的列名),
  从第二行开始每行一条数据。**不要在数据文件首插入注释或空行**
  — 解析器以第一行为 header,前面的注释会被当列名解析。
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
4. 误差传递模式还需在 "常数文件" 字段加载 ``examples/constants.txt``。
5. 点 "运行" 即可看到结果 + LaTeX + PDF 预览。

## Usage tips

- For fitting examples, the σ on the y column controls the χ² weight;
  rows without an uncertainty fall back to unit weight.
- The constants file uses the same `ALPHA value` pair-per-line format
  the error-propagation form parses.
