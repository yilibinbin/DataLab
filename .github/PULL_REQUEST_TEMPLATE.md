<!-- Thanks for contributing to DataLab! / 感谢贡献! -->

## Summary / 摘要

<!-- 1–3 bullets describing what changed and why.
     1–3 条说明改动了什么和为什么。-->

-

## Test plan / 测试计划

<!-- Bulleted checklist of how this PR was tested.
     用条目列出测试方式。-->

- [ ] `QT_QPA_PLATFORM=offscreen pytest -q` (all tests green / 全绿)
- [ ] Tested on macOS / 在 macOS 上验证
- [ ] Tested on Windows / 在 Windows 上验证(如果触及打包)
- [ ] Manual UI smoke / 手动 UI 验证(如果改动涉及前端)

## Cross-cutting checks / 跨切关注点检查

<!-- Tick what applies, see docs/ARCHITECTURE.md for the full list.
     勾选适用项,完整列表见 docs/ARCHITECTURE.md。-->

- [ ] User-facing strings go through `_dual_msg(zh, en)` (bilingual)
      用户可见字符串走 `_dual_msg(zh, en)` 双语
- [ ] mpmath calls wrap in `precision_guard(dps)`
      mpmath 调用包在 `precision_guard(dps)` 上下文里
- [ ] Expression parsing goes through `datalab_latex/expression_engine.py`
      表达式解析走 `datalab_latex/expression_engine.py` 白名单
- [ ] N/A — does not touch numerical / parsing / i18n surfaces
      不适用 — 没碰数值 / 解析 / 国际化面

## Linked issues / 关联 issue

<!-- Closes #123, refs #456 -->
