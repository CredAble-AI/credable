# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Copy `.env.example` to `.env` and set `VITE_API_MODE=live` to switch API providers from the built-in mock fixtures to the backend. Any unset or unrecognized value keeps the default `mock` mode.

During local development, Vite proxies `/v1` to `CREDABLE_BACKEND_ORIGIN`, which defaults to `http://127.0.0.1:8000`. Start the backend on that origin before starting the frontend. A deployed frontend still requires its web server or gateway to route the same-origin `/v1` path to the backend.

In live mode, the Evidence submission screen renders the backend-provided `demoFiles` list. It lets a reviewer download and re-upload normal, point-in-time mismatch, required-field-missing, and hash-mismatch synthetic PDFs. The labels show the expected demo path, while the actual quality status always comes from the backend response. Older backends that only return `demoFile` remain supported.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
