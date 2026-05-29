/**
 * DataLab Web Complete i18n Module
 * Full multilingual support for all pages and components
 */

(function() {
  'use strict';

  // Complete translation dictionaries
  const translations = {
    zh: {
      // Navigation
      'nav.extrapolation': '序列外推',
      'nav.uncertainty': '误差传递',
      'nav.fitting': '拟合',
      'nav.statistics': '统计',
      'nav.docs': '文档',
      'nav.docsTitle': '查看文档',

      // Brand
      'brand.subtitle': '高精度外推与误差分析工具',

      // Aria labels
      'aria.langToggle': '语言切换',
      'aria.themeToggle': '切换主题',

      // Footer
      'footer.version': 'DataLab Web - 版本 1.0',
      'footer.deployHint': '生产环境部署请参考',
      'footer.docsLink': '使用与技术文档',
      'footer.deployHintSuffix': '。',

      // Documentation page
      'docs.title': '文档',
      'docs.subtitle': 'DataLab Web 使用指南与技术文档',
      'docs.backToHome': '返回主页',
      'docs.fullDocSite': '完整文档站（MkDocs）',
      'docs.tableOfContents': '目录',
      'docs.previous': '上一页',
      'docs.next': '下一页',

      // Common buttons
      'btn.submit': '提交',
      'btn.run': '运行',
      'btn.download': '下载',
      'btn.downloadCSV': '下载 CSV',
      'btn.downloadPDF': '下载 PDF',
      'btn.generate': '生成',
      'btn.calculate': '计算',
      'btn.reset': '重置',
      'btn.export': '导出',

      // Common labels
      'label.dataInput': '数据输入',
      'label.parameters': '参数',
      'label.results': '结果',
      'label.value': '值',
      'label.latex': 'LaTeX',
      'label.plot': '图表',
      'label.uncertainty': '不确定度',
      'label.optional': '可选',
      'label.required': '必填',
      'label.method': '方法',
      'label.rows': '行数',
      'label.points': '点数',
      'label.default': '默认',
      'label.latexTable': 'LaTeX 表格',
      'label.pdfFallback': '若预览不可用，请下载 PDF 查看。',

      // Common checkboxes
      'checkbox.useFile': '使用文件输入',
      'checkbox.useDcolumn': '使用 dcolumn 对齐数值',
      'checkbox.useCaption': '使用标题',
      'checkbox.compilePDF': '尝试编译 PDF 并提供下载',
      'checkbox.generatePlots': '生成图片',
      'checkbox.useScientific': '使用科学计数法显示结果',

      // Common placeholders
      'placeholder.pasteData': '粘贴数据文本',
      'placeholder.uploadFile': '上传 UTF-8 文本文件',
      'placeholder.optionalCaption': '可选标题',
      'placeholder.latexEngine': 'pdflatex 或 xelatex 路径',

      // Common hints
      'hint.mpPrecision': '影响计算精度；留空使用默认',
      'hint.uploadUTF8': '仅支持 UTF-8 编码的文本文件',
      'hint.dataFormat': '首行表头，后续行为数据，列之间用空格或制表符分隔',

      // Extrapolation page (index.html)
      'extrap.eyebrow': '序列外推 · 高精度后处理',
      'extrap.title': '在浏览器中完成外推、误差传递、拟合与 LaTeX 生成。',
      'extrap.subtitle': '贴上多列数据，选择算法，即时得到外推结果与可复制的 LaTeX 表格/公式，适用于高精度数值外推、误差分析与理论计算后处理。',
      'extrap.chip1': '幂律 / 序列加速 / 自定义公式',
      'extrap.chip2': '误差传递 & 统计',
      'extrap.chip3': '一键 LaTeX 导出',
      'extrap.sectionData': '数据输入',
      'extrap.dataLabel': '多列外推数据',
      'extrap.dataHint': '首行作为表头，后续每行一组数据。',
      'extrap.pasteLabel': '粘贴数据文本',
      'extrap.dataExample': '示例格式：<code>A B C</code> 作为表头；数值可用空格或制表符分隔。',
      'extrap.uploadLabel': '上传 UTF-8 文本文件',
      'extrap.sectionMethod': '外推方法与参数',
      'extrap.methodLabel': '外推方法',
      'extrap.methodHint': '选择外推算法及其专用参数。',
      'extrap.methodPowerLaw': '幂律外推（三点）',
      'extrap.methodRichardson': 'Richardson 序列加速',
      'extrap.methodShanks': 'Shanks 变换 / Wynn ε',
      'extrap.methodLevinU': 'Levin u-transform',
      'extrap.methodCustom': '自定义公式 (A,B,C)',
      'extrap.methodQuadratic': '默认三点公式',
      'extrap.refColumnLabel': '参考列（用于 σ）',
      'extrap.refColumnModeAria': '参考列模式',
      'extrap.refColumnModeManual': '手动输入',
      'extrap.refColumnAutoMaxDiff': '最大差异列',
      'extrap.refColumnPlaceholder': '默认第 3 列',
      'extrap.refColumnHint': '可填表头名或列序号（1 开始），用于计算 |E∞-参考值|；或选择「最大差异列」自动选择差异最大的参考列。',
      'extrap.formulaLabel': '自定义外推公式',
      'extrap.formulaPlaceholder': '如 (C - B)^2/(B - A) + C',
      'extrap.formulaHint': '使用 A/B/C 或 x1/x2/x3 表示列；支持 Sin[x]/Cos[x]/Log[x]/Exp[x]/Sqrt[x]/Abs[x]',
      'extrap.sectionPrecision': '数值精度与 LaTeX 输出',
      'extrap.precisionHint': '精度控制和排版参数',
      'extrap.mpPrecisionLabel': '多精度 mp.dps（可选）',
      'extrap.latexPrecisionLabel': 'LaTeX 数值精度（有效位数）',
      'extrap.resultDigitsLabel': '结果不确定度有效位数',
      'extrap.captionLabel': '表格标题',
      'extrap.latexEngineLabel': 'LaTeX 引擎（可选）',
      'extrap.customFormulaLabel': '自定义公式',
      'extrap.customFormulaPlaceholder': '如 (C - B)^2/(B - A) + C 或 Exp[-x1]*Sin[x2]',
      'extrap.customFormulaHint': '使用与误差传递一致的公式解析：支持 Sin[x], Cos[x], Log[x], Exp[x], Sqrt[x]，可用 A/B/C、表头名或 x1/x2 别名。',
      'extrap.functionHelpBtn': '函数提示',
      'extrap.levinVariantLabel': 'Levin 变体',
      'extrap.levinVariantPlaceholder': 'u',
      'extrap.powerLawParamsLabel': '幂律外推参数',
      'extrap.powerExponentLabel': '固定幂指数 p（可空）',
      'extrap.powerExponentPlaceholder': '自动求解 p',
      'extrap.powerSeedLabel': 'p 初值',
      'extrap.powerSeedPlaceholder': '1.0',
      'extrap.powerSeedGuessesLabel': 'p 种子列表（可选）',
      'extrap.powerSeedGuessesPlaceholder': '如 0.5, 1, 2, -1',
      'extrap.powerSeedGuessesHint': '逗号或空格分隔；留空使用默认种子。',
      'extrap.precisionHint': '精度控制和排版参数。',
      'extrap.mpPrecisionLabel': '多精度 mp.dps（可选）',
      'extrap.mpPrecisionPlaceholder': '16',
      'extrap.mpPrecisionHint': '幂律/序列加速方法依赖高精度；留空使用默认值。',
      'extrap.resultDigitsLabel': '结果不确定度有效位数',
      'extrap.resultDigitsPlaceholder': '1',
      'extrap.latexPrecisionLabel': 'LaTeX 数值精度（有效位数）',
      'extrap.latexPrecisionPlaceholder': '20',
      'extrap.groupSizeLabel': '分组位数',
      'extrap.captionLabel': 'LaTeX Caption',
      'extrap.latexEngineLabel': 'LaTeX 引擎（可选）',
      'extrap.latexEnginePlaceholder': 'pdflatex 或 xelatex 路径',
      'extrap.btnSubmit': '运行外推并生成 LaTeX',
      'extrap.submitHint': '所有方法均沿用同一套高精度计算内核。',
      'extrap.resultsTitle': '计算结果',
      'extrap.resultsMeta': '方法：{method} · mp.dps: {precision} · 行数：{rows}',
      'extrap.formatControlLabel': '使用科学计数法显示结果',
      'extrap.formatDecimalPlacesLabel': '小数位数',
      'extrap.formatSignificantDigitsLabel': '有效位数',
      'extrap.formatDigitsLabel': '结果保留位数',
      'extrap.warningCount': '提示',
      'extrap.tableHeaderIndex': '#',
      'extrap.tableHeaderValue': '外推值',
      'extrap.tableHeaderUncertainty': '不确定度',
      'extrap.tableHeaderLatex': 'LaTeX格式',
      'extrap.plotsTitle': '外推图表 - 第{index}行',
      'extrap.plotsAlt': '外推趋势图 - 第{index}行',
      'extrap.latexCopyHint': '可直接复制到 .tex。',

      // Error propagation page (error.html)
      'error.eyebrow': '误差传递 / Error propagation',
      'error.title': '在浏览器中对带不确定度的数据执行公式计算，直接得到 σ 传递结果和 LaTeX 表格。',
      'error.subtitle': '支持 1.23(4)[-2] 记号、常数文件与 Mathematica 风格公式输入，自动完成偏导误差合成并生成可复制的 LaTeX 表格。',
      'error.chip1': '数值偏导',
      'error.chip2': 'mpmath 高精度',
      'error.chip3': '常数 + 数据共同传播',
      'error.dataLabel': '带不确定度的数据',
      'error.dataHint': '首行表头，后续行使用 1.23(4)[-2] 记号；括号表示末位不确定度，方括号为 10 的指数。',
      'error.pasteLabel': '粘贴数据文本',
      'error.dataExample': '示例：<code>E1 E2 E3</code> 作为表头；数值可用空格或制表符分隔。',
      'error.uploadLabel': '上传 UTF-8 文本文件',
      'error.formulaLabel': '误差传递公式',
      'error.formulaHint': '函数需使用 Mathematica 风格首字母大写并用中括号：如 <code>Sin[x1]</code>、<code>Log[ALPHA]</code>。',
      'error.formulaPlaceholder': '如 x1*ALPHA + x2/x3 + Sin[x3]',
      'error.formulaHelpBtn': '查看可用函数列表',
      'error.formulaExample': '可直接使用表头名或 x1/x2/x3 别名；常数名需与常数列表一致。',
      'error.methodLabel': '误差传递方法',
      'error.methodHint': '选择 Taylor 展开或 Monte Carlo 抽样；高阶 Taylor 目前支持到 2 阶。',
      'error.methodSelectLabel': '方法',
      'error.methodTaylor': 'Taylor（偏导）',
      'error.methodMonteCarlo': 'Monte Carlo',
      'error.orderLabel': '阶数',
      'error.orderHint': '1 阶：线性；2 阶：包含 Hessian 二阶贡献。',
      'error.mcSamplesLabel': 'MC 样本数',
      'error.mcSamplesHint': '样本越大越稳定，但耗时更长。',
      'error.mcSeedLabel': '随机种子（可选）',
      'error.mcSeedHint': '留空表示随机；填写整数可复现实验结果。',
      'error.constantsLabel': '常数 (可选)',
      'error.constantsHint': '与数据相同的 1.23(4)[-2] 记号，可使用文本或文件输入。',
      'error.enableConstants': '启用常数',
      'error.pasteConstants': '粘贴常数列表',
      'error.constantsExample': '示例：<code>ALPHA 7.2973525693(11)[-3]</code>',
      'error.uploadConstants': '上传常数文件',
      'error.precisionLabel': '数值精度与 LaTeX 输出',
      'error.precisionHint': '精度控制和排版参数。',
      'error.mpPrecisionLabel': '多精度 mp.dps（可选）',
      'error.mpPrecisionHint': '影响偏导与合成 σ 的精度；留空使用默认。',
      'error.latexPrecisionLabel': 'LaTeX 数值精度（有效位数）',
      'error.resultDigitsLabel': '结果不确定度有效位数',
      'error.latexEngineLabel': 'LaTeX 引擎（可选）',
      'error.btnSubmit': '运行误差传递并生成 LaTeX',
      'error.submitHint': '常数与数据的不确定度都会参与偏导合成。',
      'error.resultsTitle': '误差传递结果',
      'error.resultsMeta': 'mp.dps: {precision} · 行数: {rows}',
      'error.tableResult': '结果值',
      'error.tableUncertainty': '不确定度',
      'error.tableLatex': 'LaTeX格式',
      'error.plotLabel': '不确定度贡献分解',
      'error.plotAlt': '不确定度贡献图',

      // Fitting page (fit.html)
      'fit.eyebrow': '显式模型拟合',
      'fit.title': '用现有高精度拟合核心在浏览器里运行显式模型、输出参数和残差图。',
      'fit.subtitle': '粘贴 x,y,(σ) 数据即可运行多项式、倒数幂、Padé、幂律极限或自定义模型，展示模型参数、AIC/BIC/R²、残差与拟合曲线。',
      'fit.chip1': '显式模型',
      'fit.chip2': 'mpmath 精度控制',
      'fit.chip3': '残差/直方图可视化',
      'fit.dataLabel': '拟合数据',
      'fit.dataHint': '首行表头，至少包含 x 和 y，第三列（可选）为 σ。',
      'fit.dataExample': '支持括号不确定度格式: <code>2.1(5)</code> 或 单独sigma列: <code>x y sigma</code>',
      'fit.xColumnLabel': 'x 列名',
      'fit.xColumnPlaceholder': '默认第一列',
      'fit.targetColumnLabel': '目标列 (y)',
      'fit.targetColumnPlaceholder': '默认第二列',
      'fit.sigmaColumnLabel': 'σ 列名（可选，留空则使用 y 括号不确定度）',
      'fit.weightLabel': '统计/系统：',
      'fit.weightCheckbox': '统计误差加权 (sigma)',
      'fit.modeLabel': '拟合模式',
      'fit.modeCustom': '自定义模型表达式',
      'fit.modePoly': '多项式拟合',
      'fit.modeInverse': '1/x^p 展开',
      'fit.modePade': 'Padé 拟合',
      'fit.modePowerLimit': '幂律极限拟合',
      'fit.customExprLabel': '自定义模型表达式',
      'fit.customExprPlaceholder': '如 A*x**(-p) + C',
      'fit.customParamsLabel': '参数配置 (JSON)',
      'fit.varMappingLabel': '变量映射 (var: 列名，每行一对，留空默认 x)',
      'fit.polyDegreeLabel': '多项式最高阶',
      'fit.logScaleLabel': '坐标轴对数刻度',
      'fit.logScalePlaceholder': 'x / y / xy，留空为线性',
      'fit.btnSubmit': '运行拟合并生成 LaTeX',
      'fit.submitHint': '支持多项式、倒数幂、Padé、幂律极限和自定义表达式。',
      'fit.resultsTitle': '拟合结果 · 模型：{model}',
      'fit.resultsMeta': 'mp.dps: {precision} · 点数: {points}',
      'fit.paramsLabel': '参数',
      'fit.paramsHint': '含 ± 总不确定度。',
      'fit.paramTable': '参数',
      'fit.valueTable': '值 ± σ',
      'fit.exportParams': '导出拟合结果 CSV',
      'fit.metricsLabel': '指标',
      'fit.metricsHint': 'AIC 选型优先。',
      'fit.plotLabel': '拟合与残差图',
      'fit.plotHint': '使用 Matplotlib 渲染拟合与残差曲线。',
      'fit.summaryLabel': '拟合摘要',
      'fit.summaryHint': '包含模型指标与 AIC/χ²。',
      'fit.latexCopyHint': '可直接复制到 .tex。',
      'fit.sectionMethod': '拟合模式与参数',
      'fit.sectionMethodHint': '选择拟合模式及其专用参数。',
      'fit.powerLimitHint': '使用模板 A*x**(-p)+C，p≥0.1，参数初值沿用内置默认值。',
      'fit.resultsTitlePrefix': '拟合结果 · 模型：',

      // Statistics page (stats.html)
      'stats.eyebrow': '统计平均 / 误差权重',
      'stats.title': '对单列数据（可带 σ）计算均值、标准误差，并生成 LaTeX 摘要表。',
      'stats.subtitle': '支持加权/非加权、样本/总体，并生成可直接引用的 LaTeX 摘要表，适用于误差评估与平均值汇总。',
      'stats.chip1': 'σ 加权',
      'stats.chip2': 'mpmath 精度',
      'stats.chip3': 'LaTeX 表格',
      'stats.dataLabel': '数据',
      'stats.dataHint': '首行表头，第一列为数值，第二列（可选）为 σ。',
      'stats.dataExample': '支持格式：单列括号不确定度 <code>1.23(4)</code> 或 两列 <code>value sigma</code>。',
      'stats.modeLabel': '统计模式',
      'stats.modeHint': '选择统计方法与修正方式。',
      'stats.modeMean': '算术均值',
      'stats.modeWeighted': 'σ 加权均值',
      'stats.useSample': '使用样本统计 (n-1 校正)',
      'stats.sampleHint': '不勾选则使用总体统计 (n 除数)。样本统计用于估计总体参数，总体统计用于描述已知数据集。',
      'stats.useWeightedVariance': '使用加权方差计算',
      'stats.weightedVarianceHint': '勾选时使用加权平方和计算方差；不勾选时仅用有效点数计算非加权方差。',
      'stats.btnSubmit': '计算统计量并生成 LaTeX',
      'stats.submitHint': '如果提供 σ，将按所选模式进行权重/样本修正。',
      'stats.resultsTitle': '统计结果 · 模式：{mode}',
      'stats.resultsMeta': 'mp.dps: {precision} · 行数: {rows}',
      'stats.resultsTitlePrefix': '统计结果 · 模式：',
      'stats.coreMetrics': '核心统计量',
      'stats.metricName': '指标',
      'stats.metricValue': '值',
      'stats.metricUncertainty': '不确定度/备注',
      'stats.metricMode': '模式',
      'stats.metricCount': '数据点数',
      'stats.metricMean': '均值',
      'stats.metricStd': '标准差',
      'stats.metricMin': '最小值',
      'stats.metricMax': '最大值',
      'stats.metricEffectiveN': '有效点数 n_eff',
      'stats.metricDropped': '忽略的数据点',
      'stats.exportResult': '导出统计结果 CSV',
      'stats.exportRaw': '导出原始数据 CSV',
      'stats.plotLabel': '统计图表',
      'stats.plotAlt': '统计图表',

      // Help system
      'help.formulaTitle': '可用函数',
      'help.methodTitle': '外推方法说明',
      'help.close': '关闭',

      // Errors
      'errors.invalid_input': '输入无效。',
      'errors.missing_data': '请粘贴数据或上传文本文件。',
      'errors.missing_uncertainty_data': '请粘贴不确定度数据或上传文本文件。',
      'errors.missing_fit_data': '请粘贴拟合数据或上传文本文件。',
      'errors.missing_formula': '请输入公式。',
      'errors.file_parse_failed': '文件解析失败。',
      'errors.compute_failed': '计算失败。',
      'errors.network_error': '网络错误，请稍后重试。',
      'errors.formula_parse_failed': '公式解析失败。',
      'errors.non_positive_log_axis': '对数坐标要求数据为正。',
      'errors.help_load_failed': '加载帮助信息失败。',
      'errors.help_not_found': '未找到帮助信息。',
      'errors.unknown': '发生未知错误。',

      // Spreadsheet editor
      'spreadsheet.addCol': '+ 列',
      'spreadsheet.addRow': '+ 行',
      'spreadsheet.clear': '清除',
      'spreadsheet.textView': '文本视图',
      'spreadsheet.tableView': '表格视图',
      'spreadsheet.editData': '编辑数据',
      'spreadsheet.done': '完成',
      'spreadsheet.clickToEdit': '✎ 编辑',
      'btn.copyCode': '复制',
      'btn.copied': '已复制',
    },

    en: {
      // Navigation
      'nav.extrapolation': 'Extrapolation',
      'nav.uncertainty': 'Error Propagation',
      'nav.fitting': 'Fitting',
      'nav.statistics': 'Statistics',
      'nav.docs': 'Docs',
      'nav.docsTitle': 'View documentation',

      // Brand
      'brand.subtitle': 'High-Precision Extrapolation & Error Analysis Tool',

      // Aria labels
      'aria.langToggle': 'Language toggle',
      'aria.themeToggle': 'Toggle theme',

      // Footer
      'footer.version': 'DataLab Web - v1.0',
      'footer.deployHint': 'For production deployment, refer to',
      'footer.docsLink': 'Documentation',
      'footer.deployHintSuffix': '.',

      // Documentation page
      'docs.title': 'Documentation',
      'docs.subtitle': 'User Guide & Technical Documentation',
      'docs.backToHome': 'Back to Home',
      'docs.fullDocSite': 'Full Documentation Site (MkDocs)',
      'docs.tableOfContents': 'Table of Contents',
      'docs.previous': 'Previous',
      'docs.next': 'Next',

      // Common buttons
      'btn.submit': 'Submit',
      'btn.run': 'Run',
      'btn.download': 'Download',
      'btn.downloadCSV': 'Download CSV',
      'btn.downloadPDF': 'Download PDF',
      'btn.generate': 'Generate',
      'btn.calculate': 'Calculate',
      'btn.reset': 'Reset',
      'btn.export': 'Export',

      // Common labels
      'label.dataInput': 'Data Input',
      'label.parameters': 'Parameters',
      'label.results': 'Results',
      'label.value': 'Value',
      'label.latex': 'LaTeX',
      'label.plot': 'Plot',
      'label.uncertainty': 'Uncertainty',
      'label.optional': 'Optional',
      'label.required': 'Required',
      'label.method': 'Method',
      'label.rows': 'Rows',
      'label.points': 'Points',
      'label.default': 'Default',
      'label.latexTable': 'LaTeX Table',
      'label.pdfFallback': 'If preview is unavailable, please download the PDF.',

      // Common checkboxes
      'checkbox.useFile': 'Use file input',
      'checkbox.useDcolumn': 'Use dcolumn alignment',
      'checkbox.useCaption': 'Use caption',
      'checkbox.compilePDF': 'Compile PDF',
      'checkbox.generatePlots': 'Generate plots',
      'checkbox.useScientific': 'Use scientific notation',

      // Common placeholders
      'placeholder.pasteData': 'Paste data text',
      'placeholder.uploadFile': 'Upload UTF-8 text file',
      'placeholder.optionalCaption': 'Optional caption',
      'placeholder.latexEngine': 'pdflatex or xelatex path',

      // Common hints
      'hint.mpPrecision': 'Affects calculation precision; leave blank for default',
      'hint.uploadUTF8': 'UTF-8 encoded text files only',
      'hint.dataFormat': 'First row: headers, following rows: data, columns separated by space or tab',

      // Extrapolation page
      'extrap.eyebrow': 'Sequence Extrapolation · High-Precision',
      'extrap.title': 'Complete extrapolation, error propagation, fitting & LaTeX generation in your browser.',
      'extrap.subtitle': 'Paste multi-column data, select algorithms, instantly obtain extrapolation results and copyable LaTeX tables/formulas. Ideal for high-precision numerical extrapolation, error analysis, and theoretical computation post-processing.',
      'extrap.chip1': 'Power-law / Sequence Acceleration / Custom Formulas',
      'extrap.chip2': 'Error Propagation & Statistics',
      'extrap.chip3': 'One-Click LaTeX Export',
      'extrap.sectionData': 'Data Input',
      'extrap.dataLabel': 'Multi-column extrapolation data',
      'extrap.dataHint': 'First row as header, following rows as data sets.',
      'extrap.pasteLabel': 'Paste data text',
      'extrap.dataExample': 'Example format: <code>A B C</code> as header; values separated by space or tab.',
      'extrap.uploadLabel': 'Upload UTF-8 text file',
      'extrap.sectionMethod': 'Extrapolation Method & Parameters',
      'extrap.methodLabel': 'Extrapolation method',
      'extrap.methodHint': 'Choose extrapolation algorithm and its specific parameters.',
      'extrap.methodPowerLaw': 'Power-law Extrapolation (3-point)',
      'extrap.methodRichardson': 'Richardson Sequence Acceleration',
      'extrap.methodShanks': 'Shanks Transform / Wynn ε',
      'extrap.methodLevinU': 'Levin u-transform',
      'extrap.methodCustom': 'Custom Formula (A,B,C)',
      'extrap.methodQuadratic': 'Default 3-point Formula',
      'extrap.refColumnLabel': 'Reference Column (for σ)',
      'extrap.refColumnModeAria': 'Reference column mode',
      'extrap.refColumnModeManual': 'Manual input',
      'extrap.refColumnAutoMaxDiff': 'Max-diff column',
      'extrap.refColumnPlaceholder': 'Default: 3rd column',
      'extrap.refColumnHint': 'Header name or column number (1-indexed), used to calculate |E∞-reference|; or choose “Max-diff column” to auto-select the largest-deviation reference.',
      'extrap.formulaLabel': 'Custom extrapolation formula',
      'extrap.formulaPlaceholder': 'e.g., (C - B)^2/(B - A) + C',
      'extrap.formulaHint': 'Use A/B/C or x1/x2/x3 for columns; supports Sin[x]/Cos[x]/Log[x]/Exp[x]/Sqrt[x]/Abs[x]',
      'extrap.sectionPrecision': 'Numerical Precision & LaTeX Output',
      'extrap.precisionHint': 'Precision control and formatting',
      'extrap.mpPrecisionLabel': 'Multi-precision mp.dps (optional)',
      'extrap.latexPrecisionLabel': 'LaTeX precision (significant digits)',
      'extrap.groupSizeLabel': 'Group size',
      'extrap.resultDigitsLabel': 'Result uncertainty significant digits',
      'extrap.captionLabel': 'Table caption',
      'extrap.latexEngineLabel': 'LaTeX engine (optional)',
      'extrap.customFormulaLabel': 'Custom formula',
      'extrap.customFormulaPlaceholder': 'e.g., (C - B)^2/(B - A) + C or Exp[-x1]*Sin[x2]',
      'extrap.customFormulaHint': 'Same parser as error propagation: supports Sin[x], Cos[x], Log[x], Exp[x], Sqrt[x]; use A/B/C, headers, or x1/x2 aliases.',
      'extrap.functionHelpBtn': 'Function help',
      'extrap.levinVariantLabel': 'Levin variant',
      'extrap.levinVariantPlaceholder': 'u',
      'extrap.powerLawParamsLabel': 'Power-law parameters',
      'extrap.powerExponentLabel': 'Fixed power exponent p (optional)',
      'extrap.powerExponentPlaceholder': 'Solve p automatically',
      'extrap.powerSeedLabel': 'p initial guess',
      'extrap.powerSeedPlaceholder': '1.0',
      'extrap.powerSeedGuessesLabel': 'p seed list (optional)',
      'extrap.powerSeedGuessesPlaceholder': 'e.g., 0.5, 1, 2, -1',
      'extrap.powerSeedGuessesHint': 'Comma or whitespace separated; leave blank to use defaults.',
      'extrap.mpPrecisionHint': 'Power-law/sequence acceleration benefits from high precision; leave blank for default.',
      'extrap.warningCount': 'Warnings',
      'extrap.plotsTitle': 'Extrapolation plot - Row {index}',
      'extrap.plotsAlt': 'Extrapolation trend plot - Row {index}',
      'extrap.latexCopyHint': 'Copy directly into a .tex file.',
      'extrap.btnSubmit': 'Run Extrapolation & Generate LaTeX',
      'extrap.submitHint': 'All methods share the same high-precision core.',
      'extrap.resultsTitle': 'Extrapolation Results',
      'extrap.resultsMeta': 'mp.dps: {precision} · Method: {method} · Rows: {rows}',
      'extrap.formatDecimalPlacesLabel': 'Decimal places',
      'extrap.formatSignificantDigitsLabel': 'Significant digits',
      'extrap.formatDigitsLabel': 'Display digits',
      'extrap.warningLabel': 'Warnings',
      'extrap.tableResult': 'Extrapolated Value',
      'extrap.tableUncertainty': 'Uncertainty',
      'extrap.tableLatex': 'LaTeX Format',
      'extrap.downloadCSV': 'Download CSV',
      'extrap.plotsLabel': 'Extrapolation Trend Plots',
      'extrap.plotsHint': 'Rendered with Matplotlib showing data points and fitted curves.',
      'extrap.latexLabel': 'LaTeX Table',
      'extrap.pdfFallback': 'If preview unavailable, use "Download PDF" to open in system viewer.',

      // Error propagation page
      'error.eyebrow': 'Error Propagation',
      'error.title': 'Compute formula on data with uncertainties in browser, get σ propagation results and LaTeX tables.',
      'error.subtitle': 'Supports 1.23(4)[-2] notation, constants file & Mathematica-style formulas. Auto-computes partial derivatives and uncertainty synthesis.',
      'error.chip1': 'Numerical derivatives',
      'error.chip2': 'mpmath high-precision',
      'error.chip3': 'Constants + data propagation',
      'error.dataLabel': 'Data with uncertainties',
      'error.dataHint': 'First row: headers, following rows use 1.23(4)[-2] notation; parenthesis for last-digit uncertainty, brackets for 10\'s exponent.',
      'error.pasteLabel': 'Paste data text',
      'error.dataExample': 'Example: <code>E1 E2 E3</code> as headers; values separated by space or tab.',
      'error.uploadLabel': 'Upload UTF-8 text file',
      'error.formulaLabel': 'Error propagation formula',
      'error.formulaHint': 'Functions use Mathematica-style capitalized names with square brackets: e.g., <code>Sin[x1]</code>, <code>Log[ALPHA]</code>.',
      'error.formulaPlaceholder': 'e.g., x1*ALPHA + x2/x3 + Sin[x3]',
      'error.formulaHelpBtn': 'View available functions',
      'error.formulaExample': 'Use header names or x1/x2/x3 aliases; constant names must match constants list.',
      'error.methodLabel': 'Propagation Method',
      'error.methodHint': 'Choose Taylor expansion or Monte Carlo sampling; Taylor currently supports up to order 2.',
      'error.methodSelectLabel': 'Method',
      'error.methodTaylor': 'Taylor (derivative)',
      'error.methodMonteCarlo': 'Monte Carlo',
      'error.orderLabel': 'Order',
      'error.orderHint': 'Order 1: linear; order 2: includes Hessian contributions.',
      'error.mcSamplesLabel': 'MC samples',
      'error.mcSamplesHint': 'More samples are more stable but slower.',
      'error.mcSeedLabel': 'Seed (optional)',
      'error.mcSeedHint': 'Leave blank for random; set an integer for reproducibility.',
      'error.constantsLabel': 'Constants (optional)',
      'error.constantsHint': 'Same 1.23(4)[-2] notation as data, can use text or file input.',
      'error.enableConstants': 'Enable constants',
      'error.pasteConstants': 'Paste constants list',
      'error.constantsExample': 'Example: <code>ALPHA 7.2973525693(11)[-3]</code>',
      'error.uploadConstants': 'Upload constants file',
      'error.precisionLabel': 'Numerical Precision & LaTeX Output',
      'error.precisionHint': 'Precision control and formatting.',
      'error.mpPrecisionLabel': 'Multi-precision mp.dps (optional)',
      'error.mpPrecisionHint': 'Affects derivative and synthesis precision; leave blank for default.',
      'error.latexPrecisionLabel': 'LaTeX precision (significant digits)',
      'error.resultDigitsLabel': 'Result uncertainty significant digits',
      'error.latexEngineLabel': 'LaTeX engine (optional)',
      'error.btnSubmit': 'Run Error Propagation & Generate LaTeX',
      'error.submitHint': 'Uncertainties from both constants and data participate in derivative synthesis.',
      'error.resultsTitle': 'Error Propagation Results',
      'error.resultsMeta': 'mp.dps: {precision} · Rows: {rows}',
      'error.tableResult': 'Result Value',
      'error.tableUncertainty': 'Uncertainty',
      'error.tableLatex': 'LaTeX Format',
      'error.plotLabel': 'Uncertainty Contribution Breakdown',
      'error.plotAlt': 'Uncertainty contribution plot',

      // Fitting page
      'fit.eyebrow': 'Explicit Model Fitting',
      'fit.title': 'Use the high-precision fitting core in browser to run explicit models and output parameters and residual plots.',
      'fit.subtitle': 'Paste x,y,(σ) data to run polynomial, inverse-power, Padé, power-limit, or custom models, then inspect parameters, AIC/BIC/R², residuals, and fitted curves.',
      'fit.chip1': 'Explicit models',
      'fit.chip2': 'mpmath precision control',
      'fit.chip3': 'Residual/histogram visualization',
      'fit.dataLabel': 'Fitting data',
      'fit.dataHint': 'First row: headers, must include at least x and y, third column (optional) is σ.',
      'fit.dataExample': 'Supports parenthesis uncertainty: <code>2.1(5)</code> or separate sigma column: <code>x y sigma</code>',
      'fit.xColumnLabel': 'x column name',
      'fit.xColumnPlaceholder': 'Default: first column',
      'fit.targetColumnLabel': 'Target column (y)',
      'fit.targetColumnPlaceholder': 'Default: second column',
      'fit.sigmaColumnLabel': 'σ column name (optional, leave blank to use y parenthesis uncertainty)',
      'fit.weightLabel': 'Statistical/Systematic:',
      'fit.weightCheckbox': 'Statistical error weighting (sigma)',
      'fit.modeLabel': 'Fitting mode',
      'fit.modeCustom': 'Custom model expression',
      'fit.modePoly': 'Polynomial fit',
      'fit.modeInverse': '1/x^p expansion',
      'fit.modePade': 'Padé fit',
      'fit.modePowerLimit': 'Power-law limit fit',
      'fit.customExprLabel': 'Custom model expression',
      'fit.customExprPlaceholder': 'e.g., A*x**(-p) + C',
      'fit.customParamsLabel': 'Parameter config (JSON)',
      'fit.varMappingLabel': 'Variable mapping (var: column name, one pair per line, default x if blank)',
      'fit.polyDegreeLabel': 'Polynomial max degree',
      'fit.logScaleLabel': 'Axis log scale',
      'fit.logScalePlaceholder': 'x / y / xy, leave blank for linear',
      'fit.btnSubmit': 'Run Fitting & Generate LaTeX',
      'fit.submitHint': 'Supports polynomial, inverse-power, Padé, power-limit, and custom expressions.',
      'fit.resultsTitle': 'Fitting Results · Model: {model}',
      'fit.resultsMeta': 'mp.dps: {precision} · Points: {points}',
      'fit.paramsLabel': 'Parameters',
      'fit.paramsHint': 'Including ± total uncertainty.',
      'fit.paramTable': 'Parameter',
      'fit.valueTable': 'Value ± σ',
      'fit.exportParams': 'Export fitting results CSV',
      'fit.metricsLabel': 'Metrics',
      'fit.metricsHint': 'Includes AIC/BIC for manual model comparison.',
      'fit.plotLabel': 'Fitting & Residual Plots',
      'fit.plotHint': 'Rendered with Matplotlib showing fitted and residual curves.',
      'fit.summaryLabel': 'Fit Summary',
      'fit.summaryHint': 'Includes model metrics with AIC/χ².',
      'fit.latexCopyHint': 'Can be directly copied to .tex file.',
      'fit.sectionMethod': 'Fitting Mode & Parameters',
      'fit.sectionMethodHint': 'Choose fitting mode and its specific parameters.',
      'fit.powerLimitHint': 'Uses template A*x**(-p)+C, p≥0.1; parameter seeds follow built-in defaults.',
      'fit.resultsTitlePrefix': 'Fitting Results · Model:',

      // Statistics page
      'stats.eyebrow': 'Statistical Average / Error Weighting',
      'stats.title': 'Calculate mean, standard error for single-column data (with optional σ), generate LaTeX summary table.',
      'stats.subtitle': 'Supports weighted/unweighted, sample/population, generates citation-ready LaTeX summary table for error assessment and average summary.',
      'stats.chip1': 'σ weighting',
      'stats.chip2': 'mpmath precision',
      'stats.chip3': 'LaTeX table',
      'stats.dataLabel': 'Data',
      'stats.dataHint': 'First row: header, first column: values, second column (optional): σ.',
      'stats.dataExample': 'Supported formats: single column parenthesis <code>1.23(4)</code> or two columns <code>value sigma</code>.',
      'stats.modeLabel': 'Statistical mode',
      'stats.modeHint': 'Choose statistical method and correction.',
      'stats.modeMean': 'Arithmetic mean',
      'stats.modeWeighted': 'σ weighted mean',
      'stats.useSample': 'Use sample statistics (n-1 correction)',
      'stats.sampleHint': 'Unchecked uses population statistics (n divisor). Sample statistics for population parameter estimation, population statistics for known dataset description.',
      'stats.useWeightedVariance': 'Use weighted variance calculation',
      'stats.weightedVarianceHint': 'Checked uses weighted sum of squares for variance; unchecked uses effective count for unweighted variance.',
      'stats.btnSubmit': 'Calculate Statistics & Generate LaTeX',
      'stats.submitHint': 'If σ provided, will apply weighting/sample correction as selected.',
      'stats.resultsTitle': 'Statistics Results · Mode: {mode}',
      'stats.resultsMeta': 'mp.dps: {precision} · Rows: {rows}',
      'stats.resultsTitlePrefix': 'Statistics Results · Mode:',
      'stats.coreMetrics': 'Core Statistics',
      'stats.metricName': 'Metric',
      'stats.metricValue': 'Value',
      'stats.metricUncertainty': 'Uncertainty/Notes',
      'stats.metricMode': 'Mode',
      'stats.metricCount': 'Data points',
      'stats.metricMean': 'Mean',
      'stats.metricStd': 'Standard deviation',
      'stats.metricMin': 'Minimum',
      'stats.metricMax': 'Maximum',
      'stats.metricEffectiveN': 'Effective count n_eff',
      'stats.metricDropped': 'Dropped data points',
      'stats.exportResult': 'Export statistics CSV',
      'stats.exportRaw': 'Export raw data CSV',
      'stats.plotLabel': 'Statistical Charts',
      'stats.plotAlt': 'Statistical chart',

      // Help system
      'help.formulaTitle': 'Available Functions',
      'help.methodTitle': 'Extrapolation Method Description',
      'help.close': 'Close',

      // Errors
      'errors.invalid_input': 'Invalid input.',
      'errors.missing_data': 'Please paste data or upload a text file.',
      'errors.missing_uncertainty_data': 'Please paste uncertainty data or upload a text file.',
      'errors.missing_fit_data': 'Please paste fitting data or upload a text file.',
      'errors.missing_formula': 'Please enter a formula.',
      'errors.file_parse_failed': 'Failed to parse file.',
      'errors.compute_failed': 'Computation failed.',
      'errors.network_error': 'Network error. Please try again.',
      'errors.formula_parse_failed': 'Failed to parse formula.',
      'errors.non_positive_log_axis': 'Log-scale axis requires positive values.',
      'errors.help_load_failed': 'Failed to load help information.',
      'errors.help_not_found': 'Help information not found.',
      'errors.unknown': 'An unknown error occurred.',

      // Spreadsheet editor
      'spreadsheet.addCol': '+ Column',
      'spreadsheet.addRow': '+ Row',
      'spreadsheet.clear': 'Clear',
      'spreadsheet.textView': 'Text View',
      'spreadsheet.tableView': 'Table View',
      'spreadsheet.editData': 'Edit Data',
      'spreadsheet.done': 'Done',
      'spreadsheet.clickToEdit': '✎ Edit',
      'btn.copyCode': 'Copy',
      'btn.copied': 'Copied',
    }
  };

  // Current language
  let currentLang = localStorage.getItem('datalab_lang') || 'zh';

  // i18n module
  const i18nModule = {
    /**
     * Get translation for a key
     */
    t: function(key, params) {
      const dict = translations[currentLang] || translations.zh;
      let text = dict[key] || key;

      // Simple parameter interpolation: {param}
      if (params) {
        for (const [key, value] of Object.entries(params)) {
          text = text.replace(new RegExp(`\\{${key}\\}`, 'g'), value);
        }
      }

      return text;
    },

    /**
     * Set current language
     */
    setLang: function(lang) {
      if (translations[lang]) {
        currentLang = lang;
        localStorage.setItem('datalab_lang', lang);
        document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
      }
    },

    /**
     * Get current language
     */
    getLang: function() {
      return currentLang;
    },

    /**
     * Apply i18n to all elements with data-i18n attribute
     */
    applyI18n: function(root) {
      const scope = root || document;
      const queryAll = (selector) => {
        const nodes = [];
        try {
          if (scope && scope.nodeType === 1 && scope.matches && scope.matches(selector)) {
            nodes.push(scope);
          }
        } catch (e) {}
        try {
          if (scope && scope.querySelectorAll) {
            nodes.push(...scope.querySelectorAll(selector));
          } else {
            nodes.push(...document.querySelectorAll(selector));
          }
        } catch (e) {}
        return nodes;
      };

      queryAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (key) {
          let params = null;
          const paramsAttr = el.getAttribute('data-i18n-params');
          if (paramsAttr) {
            try {
              params = JSON.parse(paramsAttr);
            } catch (e) {
              params = null;
            }
          }
          const translated = this.t(key, params || undefined);

          // Handle different element types
          if (el.tagName === 'INPUT') {
            if (el.type === 'text' || el.type === 'number') {
              // Don't change value, only placeholder
              return;
            }
          }

          const hasInteractiveChildren = el.querySelector && el.querySelector('a, input, select, textarea, button');
          const wantsHtml = el.hasAttribute('data-i18n-html') || /<\/?[a-z][\s\S]*>/i.test(translated);

          if (!hasInteractiveChildren && wantsHtml) {
            // Sanitize: reject dangerous HTML patterns to prevent XSS
            if (/(<script|onerror|onclick|onload|javascript:)/i.test(translated)) {
              el.textContent = translated;
            } else {
              el.innerHTML = translated;
            }
            return;
          }

          if (hasInteractiveChildren && el.childNodes.length > 1) {
            // Complex element with mixed content - replace only text nodes
            const textNodes = Array.from(el.childNodes).filter(node => node.nodeType === Node.TEXT_NODE);
            textNodes.forEach(node => {
              if (node.textContent.trim()) {
                node.textContent = translated;
              }
            });
            return;
          }

          el.textContent = translated;
        }
      });

      // Update placeholder attributes
      queryAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (key) {
          el.placeholder = this.t(key);
        }
      });

      // Update title attributes
      queryAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (key) {
          el.title = this.t(key);
        }
      });

      // Update value attributes (for buttons)
      queryAll('[data-i18n-value]').forEach(el => {
        const key = el.getAttribute('data-i18n-value');
        if (key) {
          el.value = this.t(key);
        }
      });

      // Update aria-label attributes
      queryAll('[data-i18n-aria]').forEach(el => {
        const key = el.getAttribute('data-i18n-aria');
        if (key) {
          el.setAttribute('aria-label', this.t(key));
        }
      });

      // Update alt attributes (images)
      queryAll('[data-i18n-alt]').forEach(el => {
        const key = el.getAttribute('data-i18n-alt');
        if (!key) return;
        let params = null;
        const paramsAttr = el.getAttribute('data-i18n-params');
        if (paramsAttr) {
          try {
            params = JSON.parse(paramsAttr);
          } catch (e) {
            params = null;
          }
        }
        el.setAttribute('alt', this.t(key, params || undefined));
      });
    }
  };

  // Auto-apply i18n on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      i18nModule.setLang(currentLang);
      i18nModule.applyI18n(document.body);
    });
  } else {
    i18nModule.setLang(currentLang);
    i18nModule.applyI18n(document.body);
  }

  // Export to global scope
  window.i18nModule = i18nModule;
})();
