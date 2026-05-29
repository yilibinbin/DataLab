# DataLab Web Roadmap

This page summarizes the development roadmap for DataLab Web.

## Completed ✅

### Core Features
- Extrapolation (power-law, Richardson, Shanks, Levin u-transform, custom formula)
- Error propagation (numerical derivatives, uncertainty synthesis, constants support)
- Fitting (polynomial, inverse-power, Padé, power-limit, custom models)
- Statistics (mean, sample variance, weighted variance)
- LaTeX table generation and optional PDF compilation
- CSV export
- Dark/light theme support

### UI/UX
- Unified “?” help buttons
- Keep implementation details out of the main UI (technical info stays in docs)
- Responsive layout for mobile
- Theme toggle

### Security & Deployment
- CSRF protection
- Input validation and size limits
- Sandboxed LaTeX compilation
- Secret key configured via environment variables
- Deployment documentation (Gunicorn / Nginx)

## Short-Term (implemented) 🚀

### 1) Built-in docs pages
- Flask routes: `/docs` and `/docs/<page>`
- Markdown rendering with HTML escaping
- Whitelist mapping to prevent path traversal
- `docs.html` template and navigation entry

## Mid-Term (implemented) 🌐

### 2) Internationalization (ZH/EN)
- Frontend i18n module (`static/js/i18n.js`)
- Bilingual UI strings and a language switcher
- Remember language preference in the browser

### 3) Interactive help system
- Help specs stored in `shared/help_specs.json`
- Method help and formula function list (ZH/EN)
- “?” modal UI; help content follows language changes

## Future Ideas (planned)

### User Experience
- Interactive onboarding/tutorial
- Built-in example datasets
- Local computation history

### Features
- Batch processing (multi-file input)
- Parameter sweeps
- More extrapolation methods and fitting models

### Performance
- Result caching
- Async job queue for heavy computations

### Internationalization
- Expand bilingual docs coverage
- Additional languages

---

## Principles

1. **Security first**: validate all user input; sandbox LaTeX compilation
2. **Backward compatibility**: new features must not break existing workflows
3. **No tech stack in main UI**: technical details belong in `/docs`
4. **Single source of truth**: specs/docs/help stay consistent
5. **Progressive enhancement**: core features work without JS; JS adds convenience

## Contributing

Contributions are welcome:

1. Fork the repository and create a feature branch
2. Ensure tests pass
3. Update docs when adding features
4. Submit a pull request with a clear description
