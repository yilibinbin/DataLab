> Generated 2026-07-03 by a multi-agent swarm review (11 Claude dimension reviewers + Codex external pass). Every finding adversarially verified by 2 independent skeptics (86 candidates → 56 survived, 30 refuted), then EVERY finding re-verified line-by-line against the code (0 overturned, 40+ precision fixes applied).
> **External dual-model adversarial review: PASSED** — Codex (`VERDICT: PASS`, 0 disputes) and Gemini 3.1 Pro via Antigravity (all 9 refutation attempts failed; "100% factual"), both on 2026-07-03. Plan/analysis document — no code changed. See §六 for methodology.

# DataLab 全面蜂群审阅报告

## 一、执行摘要

DataLab 的核心数学层（`extrapolation_methods/`、`fitting/`、`datalab_core/`）架构清晰、精度纪律（`precision_guard`）执行到位，未发现数值正确性层面的严重缺陷——整体健康度良好。真正值得优先处理的问题集中在**部署可用性**与**Web 并发架构**：文档中给运维的生产启动命令（`gunicorn ... app_web.server:app`）指向一个根本不存在的符号，照做即无法启动；而同一份文档推荐的 `-w 4` 多进程部署会静默破坏进程内状态的 SSE 限流器与协作会话注册表（这既是功能 bug 也是 DoS 控制被绕过的安全问题）。第二个主题是**GUI/计算分层的裂缝**：扩展统计工作流在 Qt UI 线程上同步跑高精度计算冻结界面、顶部工具栏 Run/Stop 按钮与真实运行态脱节甚至“Run 键静默停止任务”、长任务缺乏进度反馈。第三个主题是**声称的“单一数据源”名不副实**——`ui_specs.py`、双语 `/` 分隔、`{{占位符}}` 替换、per-mode 前端胶水在桌面与 Web 各写一遍，正是项目自己想防的漂移。第四是**加速的诚实结论**：鉴于 mpmath 的任意精度本质，GPU 基本无用；真正的免费提速是安装 `gmpy2`（2–10x，零代码改动），其次是接入已经写好却处于死代码状态的 `sampling_parallel.py`。总体建议：先修 P0 部署与并发文档（低工作量、高影响），再补 GUI 分层与进度反馈，加速工作从 gmpy2 起步而非 GPU。

## 二、按严重度排序的问题清单

### [HIGH] 文档给运维的生产 WSGI 启动命令指向不存在的 `app_web.server:app`，gunicorn/waitress 无法启动

> **✅ 已修复(2026-07-03，分支 `fix/p0-deploy-wsgi`)** —— 全部 5 个部署面(deploy.en/zh、DATALAB_WEB_GUIDE.en/zh、gunicorn.conf.py)的 `app_web.server:app` 已改为工厂形式 `'app_web.server:create_app()'`（waitress 用 `--call app_web.server:create_app`）；新增 `tests/test_deploy_docs_wsgi_targets.py` 契约测试(解析所有部署面、断言每个目标可解析为 Flask app、禁止裸 `:app`)。**Codex + Gemini 3.1 Pro 双外部审阅通过。**

- **证据**: `docs/web/deploy.en.md:59`（及 :96、:115、`deploy.zh.md`）指示 `gunicorn -w 4 -b 127.0.0.1:8000 app_web.server:app` / `waitress-serve ... app_web.server:app`；但 `app_web/server.py` 只暴露 `create_app()`（:60）和 `create_app_with_socketio()`（:122），没有模块级 `app`/`application` 符号。`import app_web.server; hasattr(s,'app')` → False。
- **影响**: 运维照文档逐字执行，gunicorn 立即以 `Failed to find attribute 'app' in 'app_web.server'` 退出，生产永不启动。仅 dev 路径 `python app_web/server.py` 可用。
- **建议**: 新增模块级 `app = create_app()`（或 `wsgi.py` 定义 `application = create_app()`）并更新文档；或改文档为工厂形式 `gunicorn -w 4 'app_web.server:create_app()'` / `waitress-serve --call app_web.server:create_app`。加一个导入文档中确切目标字符串的冒烟测试。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [HIGH] 进程内 SSE 限流器与协作会话注册表是 per-process，被任何多 worker 部署静默破坏，而文档恰恰推荐 `gunicorn -w 4`（功能 + DoS 安全）

> **✅ 已按"多 worker + 诚实文档化权衡"修复(2026-07-03)** —— 经外部审阅发现:代码其实**有意**多进程(`gunicorn.conf.py:60` `_resolve_workers()` 下限设为 2，`sse.py:68` 注明"scale by processes, not threads"，因为 `_MP_SERIAL_LOCK` 把 mpmath 计算按进程串行化)。因此保留多 worker，但在全部部署面加了诚实的权衡说明:限流按 worker 计(有效额度≈`RATE_MAX_REQUESTS`×worker 数，严格全局限流应在 nginx `limit_req` 层做)、多 worker 协作需粘性会话 + 共享存储(Redis)。**并未**盲目改单 worker(那会串行化所有用户计算)。**Codex + Gemini 3.1 Pro 双外部审阅通过。**

- **证据**: SSE 限流状态 `_RATE_HISTORY: dict[str, collections.deque]`（`app_web/blueprints/sse.py:104`）加 `threading.Lock`（:105）均为进程本地；协作房间 `self._sessions`（`app_web/blueprints/collaborate.py:253`），其自身注释承认“in-memory and tied to one worker process — multi-worker collab would need Redis”（:42-43）。但 `deploy.en.md:59`（及 :96、`deploy.zh.md:58/:95`）推荐 `-w 4`；且该命令目标 `app_web.server:app` 并不存在——`app` 仅在 `server.py` 的 `__main__` 块内定义，命令按原样无法启动（另一处文档缺陷），入口一旦修正为工厂调用，多 worker 状态分裂即生效。
- **影响**: 4 workers 下 SSE 实际速率预算 ≈4×（同一客户端散列到不同 worker 绕过限制，而限流器是 DoS 控制，:90-109，安全相关）；worker A 铸造的 collab join_token 在 worker B 不可见，协作非确定性失败。
- **失败场景**: （仅适用于以多 worker 方式部署 SocketIO app 的场景——文档 gunicorn 目标对应的普通 `create_app()` 根本不注册 `/collab` 蓝图，只有 `create_app_with_socketio` 注册，`app_web/server.py:148-163`）用户 A 建会话（token 在 worker 2），用户 B 加入落到 worker 0 → “session not found”；攻击者跨 4 worker 发 40 次 SSE fit/min 永不触发 10/min 限制。
- **建议**: 文档明确多 worker 需 sticky sessions + 共享存储（Redis）支撑限流器与 collab；至少在这两个子系统假设单进程状态期间停止推荐 `-w 4`。长期以 Redis 支撑（collab extra 已注明需 Redis，`pyproject.toml:80-83`）。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

> **多源印证 / 主题关联**: 本条与下方“全局 mpmath 锁使 Web 并发上限=进程数”和“`__main__` 默认启用 SocketIO/collab”共同构成同一个 **Web 并发/部署架构** 主题——三者叠加意味着当前推荐的部署姿态在功能、安全、容量规划三方面都站不住，应作为一个 P0 波次一起处理。

### [MEDIUM] 长时高精度任务除静态 “Running” 徽章外无任何进度反馈

- **证据**: 运行中反馈仅：配置栏按钮翻转为 “Stop”（`window_extrapolation_mixin.py:135`）、结果徽章文字 “计算中/Running”（`workbench_results.py:284,332`）、状态条 “运行中/Running”（`shell_layout.py:37-39`）。运行路径（`window.py:2741` `_start_worker_with_workbench_result_state`）无 QProgressBar、无 busy spinner、无耗时计数。而 LaTeX/Tectonic 反而用了 QProgressDialog（`window_latex_compile_mixin.py:171,466`），主 mpmath 任务却没有——后者在高 dps（上限 1_000_000）恰是可跑数十秒至数分钟的操作。
- **影响**: 用户无法判断重型 LM 或 Wynn-ε 任务是在工作还是卡死，也不知已运行多久。
- **建议**: 在结果概览/状态条加不确定态 QProgressBar 或 busy 指示（复用现有 running-state 钩子），配 QElapsedTimer + 1s QTimer 的耗时标签；对已发 `log_ready` 的 worker 把最新行作为实时副标题。对齐应用已有的 LaTeX 编译反馈。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 顶部工具栏 Run/Stop 从不反映运行态；工具栏 Run 会在无确认提示下停止正在运行的任务

- **证据**: 工具栏建两个始终可见按钮 `workbench_run_button`（方法 `run_extrapolation`/`run_calculation`）与 `workbench_stop_button`（`stop_calculation`/`_stop_current_worker`）（`workbench_toolbar.py:169-192`），全仓 grep 无对二者的 setVisible/setEnabled。而 `run_calculation()` 是切换：worker 运行时调用 `_stop_current_worker()` 并返回（`window_extrapolation_mixin.py:180-184`）。此外 `run_extrapolation`/`stop_calculation` 并不存在（仅 `run_calculation`/`_stop_current_worker` 可解析）。
- **失败场景**: 启动长计算后点顶部蓝色 “Run”（仍标 Run、仍启用），`run_calculation()` 见 worker 运行即调 `_stop_current_worker()` 无确认地中止在途任务（仅日志提示“正在停止任务...”）——与标签承诺相反。
- **影响**: 两个运行控件对状态判断不一致（配置栏主按钮通过 `datalab_run_state` 正确切换，工具栏不切换）；idle 时工具栏 Stop 是死 no-op。
- **建议**: 用单一 run-state 信号驱动工具栏按钮：idle 只显示/启用 Run，运行中只显示/启用 Stop（在已存在的 `_set_button_to_stop_mode`/`_set_button_to_run_mode` 中切换）。删掉幽灵方法名 `run_extrapolation`/`stop_calculation`。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 扩展统计工作流在 Qt UI 线程同步跑计算，冻结 GUI 且无法取消

- **证据**: 对 `_DIRECT_STATISTICS_WORKFLOWS`（bootstrap_confidence_intervals、covariance_correlation、grouped_statistics、hypothesis_tests、time_series_rolling；`window_extrapolation_mixin.py:28-34`）分发器内联调用 `self._run_statistics_mode(...)`（:393），而非像其他 JobMode 那样交给后台 QThread worker（extrapolation/error/标准 statistics 构建 CalcJob + `CalcWorker`，:380-388；fitting 用 `FitWorker`；root_solving 用 `RootSolvingWorker`，:654）。这些方法直接在 UI 线程调 `create_core_session_service().submit(...)`（`window_statistics_mixin.py:504/505,607/608,800/895,1158/1159,1254/1276`）。Bootstrap CI 在 mpmath 精度下可重采样数千次，阻塞事件循环。
- **失败场景**: 选 bootstrap CI、大列多重采样、点计算 → Qt 窗口完全无响应（spinner 冻结、无重绘、无法取消）直到计算结束，macOS/Windows 可能显示 “未响应”。
- **建议**: 让 direct-statistics 走与标准统计相同的 `CalcWorker(QThread)` 路径，使 `submit()` 离开 UI 线程；并传 `cancellation_checker` 支持取消。这也消除了在 window mixin 里做重计算的分层违规。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] Fit 梯度用有限差分偏导（每次 2 次额外全评估），未用仓库已有的缓存符号偏导

- **证据**: `_build_numeric_gradient_callable`（`fitting/model_parser.py:203`）调 `shared.derivatives.numerical_partial_derivative`，每次跑两次全 `safe_eval`（`shared/derivatives.py:330` f_plus、:335 f_minus）。LM 热循环 `_gradient`（`hp_fitter.py:157-166`）每迭代遍历 N 点，每点 evaluate（1）+ partial（2），k 参数 → 每迭代 ≈k·N·3 次表达式评估。而 `shared/derivatives.py` 已有 `_get_symbolic_partials`/`_build_symbolic_partials`（sympy.diff+lambdify，LRU 缓存 64）产出精确闭式偏导——fitting 从未 import（grep 仅见 `numerical_partial_derivative`）。
- **影响**: 约 3× 冗余评估，且有限差分步长/截断误差污染 Jacobian/协方差。
- **建议**: `build_model_specification` 中先试 `_get_symbolic_partials`，命中则用 lambdified callable 作梯度函数，sympy 返 None 时回退数值偏导。约 3× 降评估并提升 Jacobian 精度。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 系统不确定度估计重跑整套多 seed 解两遍，丢弃每次重拟合昂贵的协方差/相关误差工作

- **证据**: `_estimate_systematic_uncertainty` 对 plus/minus 两方向各调 `solver(perturbed, base_seed)`（`hp_fitter.py:480-485`），即两次完整 `_run_once`。每次 `_run_once` 跑全部 seed 变体过 findroot，并经 `_process_solution`（:656-725）算 `_compute_covariance`（J^T J + `mat ** -1` 矩阵求逆，:347）、`_propagate_dependent_errors`、边界检测、全套统计。但调用方只读 `refit.params`（:496），两次重拟合的协方差/相关误差/统计全部丢弃。精度 80+ 时 k×k 求逆与逐点 Jacobian 填充占主导，白白约 3×。
- **建议**: 给 `_run_once` 加 `params_only` 快路径（跳过协方差/相关误差/多余统计，仅保留最佳候选选择所需 chi2），供两次系统重拟合使用。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] median/std/variance 的 bootstrap 每个副本都算整套描述统计

- **证据**: `_evaluate_target` 把所有非 mean 目标（median、trimmed_mean、std、variance）都路由到 `compute_statistics(...descriptive_mode...)`（`statistics_bootstrap.py:506-524`）。描述分支（`statistics_compute.py:46+`）无条件算 mean、中心平方、方差、std、完整 `sorted()`、type-7 分位数 q1/median/q3、IQR、MAD，非零方差时还算偏度、峰度——对 std/variance 只用其中一个数。这对每个副本（上限 100000，`BOOTSTRAP_MAX_RESAMPLE_COUNT`）高精度执行。
- **建议**: 加轻量 per-target 评估器（variance/std: mean + 平方 fsum；median: 单次 `_type7_quantile`；trimmed_mean: 排序+切片），`_evaluate_target` 中分发；完整 `compute_statistics` 仅保留给原样本统计。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 批量残差/Jacobian 评估才是真正的内层热点，且为逐点 Python 循环无批处理——正确的加速目标是 CPU 向量化而非 GPU

- **证据**: `_gradient`（`hp_fitter.py:157-166`）、`_compute_statistics`（:271-275）、`_compute_covariance`（:334-341）都 `for idx,(obs,target) in enumerate(zip(...))` 逐点调 `model.evaluate`/`model.partial`，各走 AST（`expression_engine._evaluate_ast`），梯度还每点每参 2 次 `safe_eval`（`derivatives.py:330,335`）。n 点 k 参每迭代 O(n·k) 全 AST 评估。解析已 lru_cache（`expression_engine.py:151`），成本在 AST 解释 + mp 算术；`model_parser.py:169` 每次重建 scope dict，无批处理。
- **建议**: 高价值加速是把模型表达式一次编译为向量化闭包一趟评估所有点（低 dps 用 numpy，或融合 mpmath 循环复用单个 scope dict），CPU 侧批处理。GPU 仅在加了低 dps float64 快路径后才有意义。配合 gmpy2 命中真实热点。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] `ExtrapolationWindow.__init__` 是 ~100 行的上帝构造函数，混杂主题接线、~40 属性、模型启发式与无名时序魔数

- **证据**: 构造函数 `window.py:477-579`：窗口尺寸 `resize(1280, 760)`、OS 主题检测+信号/定时器接线（484-500，`setInterval(5000)`）、~40 个裸属性初始化（504-562）、脆弱的 poly-baseline 启发式（519-525）、`QTimer.singleShot(500/1500,...)`（572-573）、退出钩子（574-579）。`500/1500/5000/760` 字面量无文档。3198 行 window 上帝文件的入口，无类型标注削弱 mypy。
- **建议**: 抽取 `_init_theme_wiring()`/`_init_workspace_state()`/`_init_pdf_state()`（`_init_*` 模式已存在，:566-567 调用），把 `500/1500/5000` 提升为命名模块常量。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] `ui_specs.py` 自称“single source of truth”，但 Web 前端在 i18n.js + 模板里独立重声明每个非方法标签

- **证据**: 模块头声明自己是桌面与 Web 共享的 SINGLE SOURCE OF TRUTH（`shared/ui_specs.py:6-10` 模块 docstring；未被 Web 消费的桌面专属注册表见 :756-937）。实际只有外推**方法参数**规格被共享（`app_web/blueprints/api.py:79-99` 消费 `EXTRAPOLATION_METHOD_SPECS`+`METHOD_DISPLAY_ORDER`）。grep `DESKTOP_FORM_SECTIONS`/`DESKTOP_RESULT_VIEWS`/`DESKTOP_PLOT_SPECS`/`INPUT_DATA_FIELD`/`ERROR_FORMULA_FIELD` 在 `app_web/` 零命中。Web 靠 ~1031 行手维护的 `app_web/static/js/i18n.js` 平行字符串表 + 模板硬编码（`error.html:6` '误差传递 / Error propagation' 与 `i18n.js:172` 重复）。改桌面标签会静默漂移 Web UI，docstring 误导贡献者。
- **建议**: 要么让 Web 经 JSON 端点消费 `DESKTOP_FORM_SECTIONS/RESULT_VIEWS/PLOT_SPECS`（如 `api_ui_specs` 对方法参数所做），要么修正 header 精确声明哪些注册表共享、哪些桌面专属，并加当共享标签键在 i18n.js 缺失/分歧时失败的一致性测试。别留虚假的 single source of truth 声明。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

> **多源印证 / 主题关联**: 与下方“双语 ` / ` 分割三处重实现”“`{{占位符}}` 桌面/Web 各写一遍”“per-mode 前端胶水重复”同属 **“单一数据源名不副实”** 主题——项目在参数控件上有正确的单源纪律，却在标签、分隔符、占位符、请求构建四处破例，均为已知会漂移的类别。四条合并看，优先级应提高。

### [MEDIUM] 12 个桌面 mixin 共享 ~80 个实例属性却无声明契约（无 Protocol/TYPE_CHECKING 存根），`ExtrapolationWindow` 组合未类型化且脆弱

- **证据**: `ExtrapolationWindow`（`window.py:467`）继承 QMainWindow + 7 顶层 mixin（含子 mixin 共 12 个 `window_*_mixin.py`），12 个 mixin 无一用 TYPE_CHECKING 声明借用属性（仅 window_fitting_residuals_mixin.py:90 引用 TYPE_CHECKING，且只用于导入 mpmath）。`WindowStatisticsMixin`（`window_statistics_mixin.py:243`）引用 81 个 `self.<attr>` 却只赋值 8 个，扣除该类自身定义的 25 个方法后，其余 53 个由其他 mixin/`window.__init__` 提供且无接口声明。`pyproject.toml:175-182` 仅 shared/fitting/extrapolation_methods/datalab_latex 严格，`app_desktop` 被排除，mypy 无从帮忙。`window.py` 3198 行、`window_statistics_mixin.py` 1922 行，远超用户全局编码准则的 800 行上限（该准则来自 ~/.claude/rules/common/coding-style.md，仓库自身未定文件行数准则）。
- **建议**: 引入 `_WindowProtocol`（typing.Protocol）或 TYPE_CHECKING-only 基类声明共享属性/方法，各 mixin `if TYPE_CHECKING: class X(_WindowProtocol)`，使跨 mixin 契约显式且 mypy 可检——无需过度拆分文件。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 误差传递 LaTeX 表遇任何 inf/NaN 结果（如数据单元格直接含 inf/nan，或求值无异常地产生非有限值）以 ValueError 中止，无有限性守卫

- **证据**: `_format_value_for_latex_file` → `_split_mantissa_exponent` → `int(mp.floor(...))` 对非有限输入抛 `ValueError: cannot convert inf or nan to int`（已复现）。`generate_error_propagation_table`（`datalab_latex/latex_tables_error_propagation.py:215-235`）将结果值/不确定度传入格式化时**无 try/except、无 isfinite 过滤**，不同于 `latex_tables_extrapolation.py`（:126/134/137 有 `mp.isfinite` 守卫）与统计模块。
- **失败场景**: 用户数据单元格含 'inf'/'nan'（UncertainValue/parse 接受，已复现），或计算无异常地产生非有限值 → 结果/输入列含 inf/NaN → `generate_error_propagation_table` 抛 ValueError → 整表与 PDF 导出失败，报晦涩的 'cannot convert inf or nan to int' 而非产出 ∞/NaN 单元格。
- **建议**: 格式化前守卫非有限值——跳过/替换为占位单元格（`\multicolumn{1}{c}{$\infty$}`/'NaN' 经 `siunitx_safe_cell`）或 try/except 回退转义文本，镜像 `datalab_latex/latex_tables_root.py` 的 `_number_with_uncertainty`（:162，回退在 :187-188）。同样守卫输入单元格循环。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 内联公式预览在暗色模式近乎不可见（黑字，无暗色感知颜色）

- **证据**: 内联预览标签暗色模式用暗背景 `#20242b`（`app_desktop/theme.py:253-258`），但每处桌面预览构建 `RenderRequest` **不带 color**（`formula_preview.py:218` `render_formula_pixmap`、:258 `update_formula_preview_with_empty_text` 只传 source/language/lhs）。`RenderRequest.color` 默认 `#111827`（近黑，`formula_render_service.py:29`），`render_mathtext_png` 就以该色画字。不同于 PDF 预览会在暗色反相（`pdf_preview.py:130-131`），mathtext PNG 从不反相/重着色。
- **失败场景**: 切暗色主题输入 'a*Exp[-b*x]'，内联预览显示近黑公式在暗盒上几乎不可读，仅纯文本源行（遵守暗色，`theme.py:248`）可读。
- **建议**: 在 `render_formula_pixmap`/`update_formula_preview_with_empty_text` 把主题色接入 RenderRequest（暗色时 `color='#f8fafc'`）。color 是 `_render_desktop_preview_cached` lru_cache 键（`formula_renderer.py:52-58`），明暗分别缓存、无需失效缓存；但还需在主题切换路径触发一次预览刷新（`window.py:2135` `_apply_desktop_theme` 目前不刷新公式预览，仅刷新其他工作台卡片）。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 特殊函数半数 safe-eval 白名单无 LaTeX 映射——按原文名逐字渲染（数学斜体）

- **证据**: 计算白名单（`shared/expression_engine.py:40-74`）接受 Erf/Zeta/Gamma/BesselJ/BesselY/Airy/PolyLog/Hyp0f1/1f1/2f1/Log10/Power，但渲染服务 `_FUNCTION_NAMES`（`datalab_latex/formula_render_service.py:55-73`）只识别三角/双曲/log/exp/sqrt/abs，其余走 `_escape_identifier`（:435-437）。已验证：`_source_to_latex('Erf[x]', language)`→`Erf\left(x\right)`、`'Zeta[s]'`→`Zeta\left(s\right)`、`'BesselJ[0, x]'`→`BesselJ\left(0, x\right)`、`'Log10[x]'`→`Log10\left(x\right)`（无下标）。`shared/formula_latex_export.py` 的 `_FUNCTION_COMMANDS`（:31-47）更小。
- **失败场景**: 拟合/导出 'A*Erf[b*x] + Zeta[2]'，预览与报告 LaTeX 显示 'Erf(...)'、'Zeta(2)' 为普通词，而非 `\operatorname{erf}`、`\zeta(2)`——恰是计算层宣称的特殊函数能力的保真缺口。
- **建议**: 扩展 `_FUNCTION_NAMES`（及 `_FUNCTION_COMMANDS`）加白名单特殊函数集（Erf→`\operatorname{erf}`、Zeta→`\zeta`、BesselJ/Y 阶作下标、Log10→`\log_{10}`），由单一表驱动、键自 `list_allowed_functions()`，使计算白名单与 LaTeX 映射不能漂移——镜像 expression_registry 一致性测试模式。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] SSE fit 墙钟超时形同虚设——deadline 从不中断阻塞的 fit，且进程全局 mpmath 锁被全程持有

- **证据**: `_single_fit_events` 中 `deadline = time.monotonic() + MAX_SSE_WALLCLOCK_SECONDS`，但整个 fit 在 `with _MP_SERIAL_LOCK, precision_guard(precision): ... envelope = service_factory().submit(request)` 内（`sse.py:416-435`），**无 deadline 传入、无 cancellation_checker**（核心 `SessionService` 构造时支持 `cancellation_checker`，`submit` 内经 `_CancellationToken` 生效，`session.py:114/158，但 SSE 未传）。`if time.monotonic() > deadline:`（:447）只在 submit 完全返回后执行，仅能事后发个装饰性 'Timeout'。同时 `_MP_SERIAL_LOCK`（应用级 `mpmath_lock`）全程被持，阻塞所有其他 mpmath 视图。`MAX_SSE_INPUT_POINTS=5000`、精度仅上限 1000。
- **失败场景**: GET `/api/fit/stream?x=<5000 病态点>&...&precision=1000`，1000 dps 下 5000 点线性拟合远超 90s 且持锁，同 worker 每个 `/fit` POST 与其他 SSE 请求阻塞至结束；90s 预算从不中途触发。
- **建议**: 向核心服务传取消检查器（`create_core_session_service(cancellation_checker=lambda: time.monotonic() > deadline)`），使 fitter 内 `check_cancelled()` 真正中止；或用 `KillableProcessTaskRunner` + `timeout_seconds`。docstring 的 DoS 声明（:82-88、:378-381）当前为假，不应依赖。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 可杀子进程在 terminate()+kill() 后仍存活时，worker 预算永久泄漏

- **证据**: `_finalize_if_process_dead()`（`shared/parallel_backend.py:305-317`）在 :306-307 `if self._process.is_alive(): return` 提前返回，之后才释放预算并注销句柄（:311-317）。停止路径 `_ensure_stopped()`（:297-303）与 `terminate()`（:277-284）做 `terminate();join(1.0);kill();join(1.0)`，每 join 有限 1.0s。若子进程 1s 内未死（不可中断 syscall、负载下慢回收、C 扩展中），`wait()` 的 finally（:274-275）里 `is_alive()` 仍 True，`_release_budget()` 永不调用。`_GLOBAL_WORKER_BUDGET` 永久递减，够多次后 `try_acquire` 失败、`start_killable` 抛 'worker budget exhausted'（:374-375），进程生命周期内禁用所有子进程 fit/root-solving。
- **失败场景**: CPU/IO 压力下 fit 子进程忽略 SIGTERM，SIGKILL 后两次 1.0s join 都超时，`_finalize_if_process_dead` 提前返回不释放；预算 -1 无恢复；几次后 `_execute_fit_job_payload_subprocess` 对每个后续自洽/隐式 fit 抛 RuntimeError。
- **建议**: 用一个 `_budget_released` 标志在 `wait()` 的 finally 中确定性释放一次（不依赖观察到进程已死），或在 SIGKILL 后用更长/重试的 join 再放弃（`Process.kill()` 在 POSIX 上本就发送 SIGKILL，换用 `os.kill` 并非升级）。至少在句柄仍存活时 finalize 记 ERROR 日志使泄漏可见。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [MEDIUM] 非 scan 残差容差在高 dps 下下溢，退化为松散的 1e-10 下限

- **证据**: 非 scan 残差容差用 `float(mp.eps)` 与 `math.sqrt`（`root_solving/solver.py:850-855`），高 dps 下下溢/丢精度，实际退回松散的 1e-10 下限；scan 模式用 mp 原生精度缩放容差（:862-870）。
- **失败场景**: 高 dps 下 `float(mp.eps)` 下溢，非 scan 残差容差坍缩为松散 1e-10 而非精度缩放容差。
- **建议**: 用 `mp.sqrt(mp.eps)` 计算容差，并加高精度残差测试。
- **工作量**: —（未提供）｜ **来源**: codex ｜ **验证**: CONFIRMED

### [LOW] 主 Run 按钮位于可滚动配置栏底部（需滚动才能找到按钮）

- **证据**: `left_layout` 是可滚动配置栏（`panels.py:343`，QScrollArea AlignTop 最小宽 320 竖滚动条 AsNeeded，`workbench_layout.py:57-65`）。含主 Run 按钮的 `run_section` 最后添加，在 mode/input/output_setup 之后（`panels.py:725-728,1136`）。数据表+选项卡展开、窗口较矮时 Run 按钮被推出视口下方需滚动。仅由顶部工具栏 Run 与 Ctrl+Return（:1130）部分缓解，二者对新用户不明显。
- **建议**: 将 `run_section` 移出滚动区，作为配置栏 sticky footer（加到栏 frame 而非滚动内容），主操作始终可见。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 校验与运行错误以阻塞式模态弹窗呈现，而非贴近出错字段的内联提示

- **证据**: 运行路径对输入/配置问题抛一连串 `QMessageBox.critical` 模态：坏 MC seed（`window_extrapolation_mixin.py:348`）、无效输入包（:190）、通用运行错误（:221,228,235,247,252,262,289,297,499）。每个是脱离字段的 OK-only 弹窗。应用已有内联错误面（`workbench_message_surface_style(kind="error")`、`formula_preview_error_surface_style`，`theme.py:177-193,237-242`）用于公式预览，但主运行校验未复用。
- **建议**: 字段级校验失败（seed/公式/单位/空数据）用现有错误面在相关配置卡下方内联显示，模态 QMessageBox 保留给真正不可恢复/全局失败。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 空态/首次运行结果态是裸单行标签，无下一步引导

- **证据**: 结果详情空态为单条居中标签 “暂无结果详情/No result details”（`panels.py:1162-1166`），概览 meta 读 “等待计算/Waiting for calculation”（`workbench_results.py:237`）。均不告诉新用户下一步（选模式、输入数据、按 Run）或指向 Examples。TutorialOverlay 模块虽存在（class 定义于 `tutorial_overlay.py:160`，步骤文案 `TUTORIAL_STEPS` 于 :80），但未被任何生产代码调用——仅测试与 theme.py 样式选择器引用，首次运行实际不显示任何引导，空态亦无 in-context CTA。
- **建议**: 让结果区空态可操作：短提示 + 内联 “Open an example”/“Run” 链接调现有 `open_example_workspace`/`run_calculation`，复用 theme.py 的 muted description 面。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 图标式 “?” 帮助按钮只向辅助技术暴露 “?”

- **证据**: 帮助按钮建为 `QPushButton("?")`，可访问文本注册为字面 “?”（`views/extrapolation.py:63,74`；`panels.py:765`；`views/helpers.py:103`）。不同于工具栏按钮正确设 `setAccessibleName/Description`（`workbench_toolbar.py:86-95`），这些帮助按钮不告诉屏幕阅读器打开什么主题。`use_file_hint_btn` 还设 `FocusPolicy(NoFocus)`（`panels.py:768`）移出键盘 tab 序。
- **建议**: 给每个 “?” 按钮描述性 accessibleName/description（如 “Help: extrapolation method”）并保持键盘可达，复用工具栏已用的双字符串接线。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] direct-statistics 调用点不传 cancellation_checker，尽管机制已存在却不可取消

- **证据**: `window_statistics_mixin.py` 六处 `create_core_session_service()`（:368,504,607,800,1158,1254）均无参调用，`SessionService.cancellation_checker` 为 None，`submit()` 创建的 ContextVar 取消令牌（`session.py:156-160`）无外部检查器。而 `workers_core.py` 每条 worker 路径都传 `cancellation_checker=_service_cancel_requested`（如 :945-947,1129-1131,1316-1318,1827,2615）。协作式取消设计对这些 UI 线程统计运行是惰性的。
- **建议**: 当这些工作流移到 worker 线程时，向下穿 stop-checker，并在六处传 `cancellation_checker`，对齐 `workers_core.py` 惯例。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] SessionService 的重入 busy-guard 实为死代码，因每个调用点都构造全新服务

- **证据**: `SessionService.submit()`（`session.py:146-153`）用 `self._active_request_id` 防并发并返 'busy'，但无调用方跨并发任务复用实例：Web 每请求新建（`app_web/logic/extrapolation.py:220` 等），桌面每模式/每统计调用点新建（`workers_core.py` 多处、`window_statistics_mixin.py` 六处）。全局 mp.dps 的跨请求并发安全实际由别处提供（Web: `@mpmath_synchronized` 全局锁 `security.py:190-210`；核心: `precision_guard`）。故 busy-guard、last_result、status 保护不了任何东西。
- **建议**: 要么将 SessionService 记为有意的单次/每任务并删除 busy-guard + 可变 status/last_result；要么若打算共享长寿命服务，让前端持单实例使 guard 有意义。二选一消歧。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] per-mode 前端胶水（method_options/请求参数组装 + submit/解码编排 + LaTeX/plot 渲染胶水）在桌面与 Web 各写一遍

- **证据**: 外推流程实现两次形状几乎相同：Web `app_web/logic/extrapolation.py:190-236` 建 ExtrapolationOptions/method_options（`_method_options_payload`/`_power_config_payload` :106-157）→ `build_extrapolation_request`→submit→`extrapolation_payload_to_rows/_to_results`；桌面 `app_desktop/workers_core.py:580-625`（`_safe_extrapolation_core_request`/`_extrapolation_method_options`）与 :936-957 手工同构。plot 渲染也重复（`app_desktop/workers_core.py:521-577` vs `app_web/logic/plots.py:15-76`）。method_options schema 两文件手镜像，新增选项须两处改否则静默分歧。
- **建议**: 把 method_options 组装等剩余每前端胶水（请求构建/payload 解码原语已在 `datalab_core/extrapolation.py`）提升到 `datalab_core`/`shared` 的 UI 中立 helper，两前端调用，仅留真正 UI 关切（表单读取、Qt vs base64 plot 交付）。镜像现有参数控件单源纪律。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 并行 seed-solve 在每个 worker 任务内重新 pickle 全观测集并从文本重建模型

- **证据**: `_solve_variants`（`fitting/hp_fitter.py:762-777`）每 seed 变体建一 `_SeedSolveTask`，各内嵌整份数据集副本（`observations=tuple(dict(obs) for obs in observations)`）。1+2k 变体 → 同一 N 行观测（每格 mp.mpf）被 pickle 并运 1+2k 次。`_solve_seed_variant_task`（:226-250）在每 worker 内调 `build_model_specification` 重解析表达式、重建 k 个梯度 callable。高精度 mp.mpf 序列化昂贵（`sampling_parallel.py:70-76` 故意走字符串规避）。
- **建议**: 观测/目标一次性发送（字符串化，镜像 sampling_parallel），经 ProcessPoolExecutor initializer 每 worker 重建一次模型 + 观测，每任务仅传 `(variant_index, seed_variant)`；或提高并行阈值使小 fit 跳过 pool。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 相关/协方差矩阵同时算 (i,j) 与 (j,i)，且每对重算各列均值/方差

- **证据**: `_matrix_from_row_provider`（`statistics_matrix.py:415-424`）双重 `for i/for j in range(size)`，每格从头重算 mean_left/mean_right、var_x/var_y（:448-452）。协方差/相关对称，(j,i) 重复 (i,j)，约 2× fsum/乘积。listwise 情况下列均值/方差只依赖该列却重算 size 次。高 dps 多列时 O(size²·n)，而 O(size·n) 预计算 + 上三角即可。
- **建议**: 每列均值/方差预计算一次（listwise），只填上三角并镜像到下三角；pairwise 保留 per-pair 均值但跳过冗余 (j,i)。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 未安装 gmpy2——同一 mpmath 代码上免费 2–10x 提速，令大部分 GPU 讨论失去意义

- **证据**: 全仓及所有 requirement 文件 grep `gmpy2`/`mp.libmp` 零命中。mpmath 导入时自动探测 gmpy2：有则用 GMP 支撑的整数做尾数算术，无则回退纯 Python int。默认 80 dps（~266 位尾数，`fitting/hp_fitter.py:536` 等多处默认 precision=80）下每次 mp.mpf 乘/加（残差与 Jacobian 循环 `hp_fitter.py:160-166,271-275,334-341`）跑 Python bignum。gmpy2 该区间通常 2–10x，零代码改动，mpmath 透明拾取。
- **建议**: 加 gmpy2 为可选依赖（extras `[fast]`）并写文档。`python -c "import mpmath; print(mpmath.libmp.BACKEND)"` 应打印 'gmpy'。无源码改动；precision_guard/safe_eval/LM 全自动受益。本仓单一最高性价比加速杠杆，且纯 CPU。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] sampling_parallel.py 存在但在生产中是死代码——DataLab 已建好的 CPU 并行未接入任何真实路径

- **证据**: 模块 docstring 称 “Not yet wired into sample_mp_function by default”（`fitting/sampling_parallel.py:24-27`）。grep `sample_mp_function_parallel`/`sampling_parallel` 只见 `benchmarks/test_sampling_performance.py:58,62` 与测试，无 app_desktop/app_web/datalab_core/fitting 生产调用。实际用的是串行 `fitting.plot_fitting.sample_mp_function` 做密集预览/曲线采样。
- **建议**: GPU 之前先把 `sample_mp_function_parallel` 接入密集预览/跨模型自动拟合路径（其 `PARALLEL_MIN_POINTS` 守卫已对小输入/不可 pickle callable 回退串行）。兑现已付出的加速，CPU 级，无数值正确性风险。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] `_snapshot_clean_text` 在 datalab_core 定义 3 次且语义分歧（同名三种行为）

- **证据**: 三处模块本地同名 helper 对非字符串/falsy 输入行为不同：`fitting_comparison.py:726` `str(value).strip() if value is not None else ""`（`0`→"0"、`False`→"False"）；`root_solving.py:1037` `str(value or "").strip()`（`0`/`False`/`""`→""）；`statistics.py:2733` `value if isinstance(value,str) else ""`（任何非 str 含 `0`→""）。用于 snapshot payload 字段。`datalab_core/statistics_helpers.py` 已是天然共享家。
- **失败场景**: 携整数 `0`/bool `False` 的 snapshot 字段，经 fitting_comparison 路径渲染为 "0"/"False"，经 statistics 路径为 ""，同一逻辑值因序列化模块不同而显示不同。
- **建议**: 把单一 `snapshot_clean_text`（statistics 的 `isinstance(str)` 守卫最严最安全）提升到 `statistics_helpers.py`，删三份本地副本并 import。核对契约一致后同样处理 2× `_snapshot_numeric_text`（`statistics.py:2494` vs `uncertainty.py:1180`）。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 双语 ' / ' 分割三处重实现 maxsplit 不一致；Web base.html 截断任何含 ' / ' 的英文串

- **证据**: `shared/bilingual.py:28` 规范用 `split(" / ", 1)`，桌面一致（`window_extrapolation_mixin.py:842`、`tutorial_overlay.py:131` 均 `.split(' / ', 1)`）。但 `base.html:98` 做无限制 `raw.split(' / ')` 再取 parts[0]/parts[1]。对 '比率 / ratio a / ratio b'，桌面渲染 'ratio a / ratio b'，Web 只渲染 'ratio a'。
- **失败场景**: 翻译写含 ' / ' 的英文标签（如 'mol / L'、'input / output'），Web 只渲染首个 ' / ' 前的文本静默丢弃其余，桌面正确。
- **建议**: 把 `base.html:98` 改为 `indexOf(' / ')`+slice 取右半为英文半，镜像 maxsplit=1，并加含右半斜杠串的 JS 断言。长期暴露一个规范分割器而非三份副本。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] `{{DEFAULT_THREE_POINT_FORMULA}}` 占位符替换在共享 facade（桌面帮助路径）与 Web `api_help_specs` 端点各自独立实现

- **证据**: `help_specs.json:120,125` 嵌 `{{DEFAULT_THREE_POINT_FORMULA}}`。桌面在 `formula_help.py:61-67` 用递归 `_substitute_placeholders` + `shared.formula_defaults.DEFAULT_THREE_POINT_FORMULA` 解析。Web（`api.py:212-219`）在 `api_help_specs()` 内定义自己逻辑等价（仅变量名不同：value/key/item vs obj/k/v）的递归 `_substitute_placeholders` 重读同 JSON。加第二个占位符 token 时一路替换一路不替换，产生桌面/Web 帮助不一致。
- **建议**: 让 `api_help_specs` 调共享 `formula_help` facade（已返回替换后内容），或把 `_substitute_placeholders` 移入 shared 两处 import。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 无鲁棒/M 估计拟合——仅最小二乘，单个离群点即毁全部拟合

- **证据**: 全仓 grep `huber|tukey|bisquare|soft_l1|robust|irls|m_estimator` 在 fitting/、datalab_core/、extrapolation_methods/ 无鲁棒损失实现（fitting/ 内唯一 'robust' 命中是 `plot_fitting.py:736` 的缓存注释（与鲁棒损失无关）；datalab_core/statistics.py 另有 'robust' 命中（136–374、2693–2696 行），但均为统计模式的 MAD/修正 z 分数离群点检测，非拟合鲁棒损失）。`hp_fitter.py:1` 是纯 χ²/加权最小二乘 LM。对以高精度曲线拟合为卖点的工具，缺任何抗离群损失（Huber/Tukey/Cauchy/IRLS）是显著科学功能缺口。
- **失败场景**: 拟合含一个误录点的 Arrhenius/衰减数据集，最小二乘被离群点拽偏，reduced_chi2 爆炸，用户除手删数据外无内建降权手段。
- **建议**: 给 hp_fitter 加可选损失/鲁棒加权（IRLS + Huber/Tukey 是标准低风险，复用现有 LM 内循环每迭代重加权），经 `shared/ui_specs.py` 暴露给两前端与 CLI，保持 `param_errors_stat`/`param_errors_sys` 语义。
- **工作量**: L ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 序列加速外推仅 4 个 accelerator 键（实为 3 种算法）；缺 Aitken Δ² 与 theta/rho

- **证据**: `apply_sequence_accelerator`（`extrapolation_methods/accelerators.py:38`）分发 'richardson'、'shanks'、'wynn_epsilon'（与 'shanks' 是同一 `mp.shanks` 调用，:86-90，仅元数据标签不同）、'levin_u'——实为三种不同算法。Aitken Δ²（grep 缺失）、Brezinski θ、ρ 算法均标准、廉价、对 Wynn-ε 表现不佳的对数收敛序列互补，未提供。mpmath 不带 θ/ρ，但 Aitken Δ² 仅数行。
- **失败场景**: 对数收敛序列（Wynn-ε 已知停滞）用户无备选加速器可试，尽管工具主打序列外推。
- **建议**: 至少加 Aitken Δ²（trivial 无依赖），可行则加 θ，经 `shared/ui_specs.py` 暴露。并明确文档 shanks/wynn_epsilon 重复以免误导为两独立方法。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] auto_fit_dataset 仅按 AIC 选最佳模型——无 BIC 选项、无 ΔAIC/Akaike 权重比较输出

- **证据**: `auto_fit_dataset`（`fitting/model_selector.py:254-262`）纯按最小 AIC 选（`score = result.fit_result.aic ... if score < best_score`）。BIC 已算并存于每个 FitResult（`model_selector.py:101`），比较表（`model_comparison.py:108-109`）每行带 aic/bic，但自动选择完全忽略 BIC，只报单个 best_model，无 ΔAIC、无 Akaike 权重、无 BIC 选择途径。
- **失败场景**: 两模型几乎同拟合（ΔAIC≈0.3），工具静默报一为 'best' 而不提示选择在噪声内，导致过度解读。
- **建议**: 扩展 AutoFitSummary 暴露 per-model ΔAIC/ΔBIC 与 Akaike 权重，加选择准则选项（AIC vs BIC）。输入已全算好，是聚合/呈现而非新拟合。
- **工作量**: M ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] 所有数值 Web 计算在一个进程全局 mpmath 锁上串行——“4 workers”是唯一真实 Web 并发

- **证据**: mp.dps 进程全局，故每个模式的核心计算函数（`app_web/logic/{fitting,extrapolation,statistics,root_solving,error_propagation}.py` 中的 `_run_*`，由各视图调用）被 `@mpmath_synchronized` 包裹，全函数体内持单一模块全局 `_mpmath_lock`（`app_web/security.py:190,206-209`）；SSE fit 取同锁（`sse.py:70` `_MP_SERIAL_LOCK = mpmath_lock`）全程持有（:416）。单 worker 进程内任一时刻至多一个 mpmath 计算，threaded WSGI（waitress `--threads=8`、gunicorn gthread）对核心工作零并行；一个高精度 fit（SSE 路径 `MAX_SSE_WALLCLOCK_SECONDS=90`，`sse.py:88`，但 deadline 仅在 fit 完成后检查 `sse.py:414,447`，故阻塞可达甚至超过 90s）阻塞该进程内所有数值请求。代码正确（守卫全局 mp.dps 的正确方式），但架构把 Web 吞吐上限锁在（worker 进程数）个并发计算，容量规划未文档化。
- **失败场景**: waitress `--threads=8`（`deploy.en.md:115`）下 8 个 80 位并发 fit，线程 2-8 阻塞于 `_mpmath_lock`，有效并发 1 非 8。
- **建议**: 保留锁（对 mpmath 全局 dps 是正确之举）。现代修法是把重计算移出请求 worker：任务队列（RQ/Celery）或专用计算子进程池（扩展 `parallel_backend.py`），每子进程拥有自己的 mp.dps。在 deploy.md 文档化 per-process 串行天花板，令运维按 worker 数=期望并发计算数配置。
- **工作量**: XL ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] PyInstaller spec 头声称“每次构建重生成”而 CLAUDE.md 说“不要重生成”——且开启 `upx=True`

- **证据**: `DataLab.spec:6-10` docstring 说 'regenerated by PyInstaller on each build, so do NOT edit by hand without verifying the regeneration preserves the relative-path discipline'（条件式警告，并非无条件禁止手改），但项目 CLAUDE.md 说 'spec is hand-tuned — do not regenerate'。二者直接矛盾；但失实的一侧是 CLAUDE.md——构建脚本确实每次重生成 spec（build_mac_data_gui.sh:333 以 `pyinstaller "$ENTRY_FILE" --name DataLab ...` 纯 CLI 标志构建，从不读取 .spec 文件）（53 项精选 PySide6 `excludes`（:115-140，26 行）、INFO_PLIST 文档类型块 :83-103，重生成仅丢失 spec 内的手写文档串与注释；excludes 的规范来源在 build_mac_data_gui.sh:143-203（经 `--exclude-module` 传入，spec:117-119 自述以该脚本为准），INFO_PLIST 文档类型由 build_mac_data_gui.sh:359-389 用 PlistBuddy 在构建后重打——功能配置不会丢）。EXE 与 COLLECT 均 `upx=True`（:155,169）——UPX 是 AV 误报与 macOS codesign/公证损坏的已知源，构建主机不保证有 UPX 二进制，该标志或静默 no-op 或签名隐患。
- **建议**: 修正矛盾以符实：改 CLAUDE.md:40 的 'spec is hand-tuned — do not regenerate'，改述为 spec 由构建脚本每次重生成、规范配置（excludes/文档类型）在 build_mac_data_gui.sh 中维护。对签名/公证的 macOS 与 Windows 构建在两个构建脚本加 `--noupx`（直接改 spec 的 upx=False 会在下次构建被重生成覆盖）（或门控于显式验证 UPX 存在的标志）。
- **工作量**: S ｜ **来源**: claude ｜ **验证**: CONFIRMED

### [LOW] `__main__` 总是先尝试 SocketIO/collab，与“未接入默认 web 栈”的姿态矛盾

- **证据**: `pyproject.toml:79-83` 记 collab 'Not wired into the default web stack; needs Redis for multi-worker scaling'。但 `server.py:189-200` `__main__` 无条件先调 `create_app_with_socketio()`，仅在 ModuleNotFoundError 回退 `create_app()`。`web_requirements.txt` 装 `.[web,collab,mcmc]`（含 flask-socketio），故默认 `python app_web/server.py` 静默启用 collab websocket 面 + 其内存会话注册表（`async_mode='threading'`，`server.py:157`）。“opt-in、需 Redis”子系统在 dev 默认开启，暴露其多 worker 不安全状态而运维未选择。仅 dev 入口（生产用 WSGI），故严重度受限。
- **建议**: 将 SocketIO 门控于显式环境变量/开关，默认关闭；使 dev 入口与 pyproject 声明的 opt-in 姿态一致。
- **工作量**: S（推断）｜ **来源**: claude ｜ **验证**: CONFIRMED

> 注：本条证据文本在输入 JSON 中被截断于 `recommendation: "Gate SocketIO behind an e...`。建议部分为按上下文合理补全，落地前请核对原始 finding。

## 三、按维度分组的观察

**GUI 设计与人性化（desktop UX）**：本维度是 confirmed 发现最密集处，主题一致——**运行态与反馈的缺失**。长任务无进度/耗时反馈（`workbench_results.py:332`），顶部工具栏 Run/Stop 与真实状态脱节甚至反向操作（`workbench_toolbar.py:169`），主 Run 按钮沉在可滚动栏底（`panels.py:728`），错误用模态弹窗而非内联（`window_extrapolation_mixin.py:190`），空态无引导（`panels.py:1162`），“?” 按钮对辅助技术不透明（`panels.py:765`）。这些多为 S/M 工作量，集中在“让用户随时知道系统在做什么、下一步做什么”。

**GUI/计算分离（layer boundaries）**：核心裂缝是扩展统计在 UI 线程同步计算（`window_extrapolation_mixin.py:392` + `window_statistics_mixin.py` 六站点），既冻结界面又违反分层；连带这些站点不传 cancellation_checker（机制存在却惰性）。此外 `SessionService` 的 busy-guard 因每次新建实例而成死代码，per-mode 前端胶水桌面/Web 重复——两者都是“分层意图与实际接线不符”的清晰化问题。

**后端性能（compute performance）**：全部是“重算/冗余评估”类，无正确性风险。梯度用有限差分而非已有符号偏导（3× 评估 + 精度损失）、系统不确定度重跑两遍并丢弃协方差、bootstrap 每副本算整套描述统计、协方差矩阵算双三角并重算列统计、并行 seed-solve 重 pickle 全数据。真正内层热点是逐点 AST 评估的批处理缺失。

**GPU 加速可行性**：见专题第四节。核心结论——GPU 对任意精度 mpmath 基本无用；免费大提速在 gmpy2 与接入死代码 `sampling_parallel.py`。

**代码质量**：`ExtrapolationWindow.__init__` 上帝构造函数与时序魔数（`window.py:477`）、`_snapshot_clean_text` 三处分歧副本（`statistics.py:2733` 等）。均为局部清晰化，风险低。

**维护性**：统一主题是**“单一数据源”名不副实**——`ui_specs.py` 头部虚假声明（:6-10；桌面专属注册表见 :756-937）、双语 `/` 分割三处 maxsplit 不一致、`{{占位符}}` 桌面/Web 各写、12 mixin 无类型契约。四条叠加显示项目的单源纪律只在参数控件上兑现，其余四类均已知会漂移。

**功能支持与完整度**：三个科学能力缺口——无鲁棒/M 估计拟合（离群点毁全拟合）、序列加速器实为 3 算法（缺 Aitken Δ²/θ/ρ）、auto-fit 仅 AIC 无 ΔAIC/BIC/Akaike 权重。均为“对标一个科学工具箱应有的下限”的补全，非 bug。

**现代化设计（architecture & stack）**：最高严重度集中于此——文档生产启动命令不存在（HIGH）、多 worker 破坏进程内状态（HIGH），加上全局锁并发天花板、`__main__` 默认开 collab、PyInstaller spec 矛盾 + UPX 隐患。主题是**部署姿态与真实运行时/安全属性不一致**。

**LaTeX 输出**：单点但真实的导出中断——误差传递表遇 inf/NaN 抛 ValueError 使整个 PDF 导出失败（`latex_tables_error_propagation.py:226`），而外推/统计路径已有 isfinite 守卫，此处独缺。

**公式渲染**：两条保真缺口——暗色模式内联公式近黑不可读（`formula_preview.py:218`）、特殊函数白名单半数无 LaTeX 映射渲染为原文（`formula_render_service.py:55`）。后者恰是计算层宣称能力的表现层缺口。

**Bug 与正确性风险**：SSE 超时形同虚设 + 全局锁全程持有（`sse.py:414`）、worker 预算永久泄漏（`parallel_backend.py:305`）、非 scan 残差容差高 dps 下溢退化为 1e-10（codex，`solver.py:850`）。前两条是资源/DoS 相关的真实运行时缺陷，第三条是高精度场景静默精度退化。

## 四、GPU 加速专题（诚实结论）

**核心判断：对本代码库，GPU 加速在其主打的高精度路径上基本无用，且会误导优化投入方向。**

原因：DataLab 的数值核心是 mpmath 任意精度（默认 80 dps ≈266 位尾数），其瓶颈是**软件 bignum 尾数算术 + AST 解释**（`hp_fitter.py:160-166,271-275,334-341`；`expression_engine._evaluate_ast`），而非可映射到 GPU SIMD 的 float32/float64 密集线代。GPU 擅长的是大规模低精度并行浮点，与“每个 mp.mpf 乘法是一串 Python 层 bignum 运算”的负载画像正交。要让 GPU 有意义，必须先引入一条 **低 dps float64 快路径**（本身是独立的、有数值精度取舍的工程），届时 GPU 才有可批处理的对象——但那时你已经离开了工具箱的核心卖点（高精度）。

**真正该做的、按性价比排序（全部 CPU 侧、零/低数值风险）**：

1. **安装 gmpy2（S 工作量，2–10x，零代码改动）** —— mpmath 导入时透明拾取 GMP 尾数算术，`precision_guard`/`safe_eval`/LM 全自动受益。这是单一最高性价比杠杆，应在任何加速讨论之前完成。
2. **接入已死的 `sampling_parallel.py`（M）** —— 密集预览/跨模型自动拟合的采样是天然可并行路径，模块已写好、已测、有 `PARALLEL_MIN_POINTS` 守卫与串行回退，却无生产调用者。兑现已付出的加速，无正确性风险。
3. **模型表达式向量化 / 批处理残差与 Jacobian（L）** —— 把 per-point 的 AST 树遍历解释 + scope-dict 重建（`model_parser.py:169`；AST 本身仅解析一次并缓存）折叠为一趟批评估。这是真正的内层热点，且是 CPU 向量化而非 GPU 的目标。
4. **消除冗余评估（M，见性能维度）** —— 符号偏导替代有限差分、系统不确定度 params_only 快路径、bootstrap per-target 评估器、协方差上三角。

**结论一句话**：先装 gmpy2、接死代码并行、批处理内层循环；GPU 只有在你愿意为它专门建低精度快路径时才谈得上，而那与本工具箱的高精度定位相冲突。

## 五、优先级路线图

按“风险排序”分波（用户已说明忽略重构难度，故此处只按运行时风险/影响/依赖排序，不按工作量大小）。

### P0 — 立即（部署即坏 / 安全 / 数据损坏）
- **[HIGH] 文档生产启动命令指向不存在的 `app_web.server:app`**（`deploy.en.md:59`）——照做即无法启动，最高影响、S 工作量，先修。
- **[HIGH] 多 worker 破坏进程内 SSE 限流器与 collab 注册表**（`sse.py:104` / `app_web/blueprints/collaborate.py:253`）——功能 + DoS 安全双重问题；至少立即从文档移除 `-w 4` 推荐（文档改动 S），Redis 化为后续。
- **[MEDIUM] 误差传递表 inf/NaN 抛 ValueError 中止整个 PDF 导出**（`latex_tables_error_propagation.py:226`）——用户可触发的导出崩溃，S 工作量，加 isfinite 守卫。
- **[MEDIUM] worker 预算永久泄漏**（`parallel_backend.py:305`）——一旦触发则进程内所有子进程 fit 永久禁用；确定性释放修法 M。
- **[MEDIUM] SSE 超时形同虚设 + 全局锁全程持有**（`sse.py:414`）——单请求可长时间钉死 worker 与全局锁，与 P0 并发主题同源。

> P0 的四条现代化/并发条目（启动命令、多 worker 状态、SSE 超时、全局锁天花板 + `__main__` 默认 collab）应作为**一个部署审计波次**统一处理——它们共享同一根因：部署文档与真实运行时/安全属性不一致。

### P1 — 近期（用户可见质量 / 分层健康）
- **[MEDIUM] 扩展统计冻结 UI 线程**（`window_extrapolation_mixin.py:392`）——移到 QThread 并接 cancellation。
- **[MEDIUM] 顶部工具栏 Run 静默停止任务**（`workbench_toolbar.py:169`）——单信号驱动、删幽灵方法名，S。
- **[MEDIUM] 长任务无进度反馈**（`workbench_results.py:332`）。
- **[MEDIUM] 非 scan 残差容差高 dps 下溢**（`solver.py:850`，codex）——用 `mp.sqrt(mp.eps)`，加高精度测试。
- **[MEDIUM] 暗色模式公式不可读**（`formula_preview.py:218`）+ **特殊函数无 LaTeX 映射**（`formula_render_service.py:55`）——渲染保真。
- **[S 免费提速] 安装 gmpy2** —— 独立、零风险、高回报，可随时插入。

### P2 — 择机（清晰化 / 性能重算 / 功能补全）
- 维护性单源修复（`ui_specs.py` 头 / 双语分割 / 占位符 / mixin Protocol）——同一主题批量处理。
- 性能重算类（符号偏导、系统不确定度 params_only、bootstrap per-target、协方差上三角、seed-solve 序列化、批处理内层循环）+ 接入 `sampling_parallel.py`。
- 代码质量（`__init__` 上帝构造、`_snapshot_clean_text` 三副本）。
- 功能补全（鲁棒/IRLS 拟合、Aitken Δ² 等加速器、ΔAIC/BIC/Akaike 权重）。
- GUI 打磨（主 Run 按钮 sticky、内联校验错误、空态 CTA、“?” 可访问性）。
- PyInstaller spec 头矛盾修正 + `upx=False`。
- Web 并发架构升级（任务队列/计算子进程池，XL）——最大工作量，无功能回归压力，最后做。

## 六、方法与置信度说明

- **来源**：主体由内部蜂群（source=claude，11 个维度审阅员）产出，一条外部来源为 codex（非 scan 残差容差下溢，`solver.py:850`）。
- **外部模型覆盖（诚实声明）**：初始蜂群阶段计划结合两个外部模型，但当时 Gemini CLI 认证失败（`IneligibleTierError`），初始发现来源实际只有 Codex 一个外部模型。**后续已补齐**：改走 Antigravity CLI（`agy`）通道后，最终文档于 2026-07-03 通过 **Codex + Gemini 3.1 Pro (High)** 双外部模型对抗性审阅——Codex `VERDICT: PASS`（0 异议，全查 HIGH、抽查 13 条 MEDIUM、运行时验证 `mpmath.libmp.BACKEND=python`/gmpy2 不可导入），Gemini 9 项定向反驳尝试全部失败（结论 "100% factual"）。
- **规模**：内部原始 findings 64 条 + 外部来源 codex；候选 86 条；经对抗性验证存活 56 条，反驳/剔除 30 条（refuted=30）。本报告呈现的是其中提供给 lead 的 40 条 CONFIRMED 子集。
- **验证状态**：本次交付的全部发现均标记 **CONFIRMED**（多条附有直接复现，如 inf/NaN ValueError、`hasattr(s,'app')`→False、`_source_to_latex` 输出、`_snapshot_clean_text` 三态差异）。输入中**未包含任何 PLAUSIBLE 条目**——即无“合理但未证实”的悬置发现进入本报告；未存活的 30 条已在验证阶段剔除，不在此列。
- **诚实边界**：（1）codex 条目缺 effort 字段，路线图中按影响排入 P1。（2）最后一条 `__main__` 默认 collab 的原始 `recommendation` 文本在输入 JSON 中被截断（`...behind an e`），其证据完整、结论可靠，但建议措辞为按上下文补全，落地前应核对原始 finding。（3）多处“多源印证”标注反映的是同一 source 从不同维度重复触及同一主题（部署并发、单一数据源），据此提升了优先级而非独立置信度。
- **二次逐条再验证（2026-07-03）**：全部 38 条发现 + §三/§四/§五 章节论述又经过一轮独立的逐条 pedantic 事实核查（每条一个全新验证员，严查 file:line、引用拼写、因果主张、建议与项目不变量的兼容性）。结果：**0 条核心主张被推翻**；19 条完全准确，19 条应用了共 40+ 处精化修正（行号校准、路径全称、措辞限定——最实质的一处：collab 跨 worker 失败场景仅适用于 SocketIO 部署，文档推荐的 `create_app()` 部署不注册 `/collab` 蓝图）。
- **总体置信度**：高。发现集中在可静态核验的部署配置、分层接线、渲染映射与算法冗余，均可溯源到 file:line；数学正确性层面（除 codex 的容差下溢外）未发现严重缺陷，与该核心层的成熟度评估一致。