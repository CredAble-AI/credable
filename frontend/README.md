# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Development and production use the live backend by default. Set `VITE_API_MODE=mock` only when intentionally previewing the built-in fixture providers without a backend; tests default to mock mode. `CREDABLE_BACKEND_ORIGIN` configures the Vite development proxy target.

Customer-facing technical metadata is hidden by default. Set `VITE_SHOW_CUSTOMER_TECHNICAL_DETAILS=true` only during local debugging; keep it disabled in the judging demo.

During local development, Vite proxies `/v1` to `CREDABLE_BACKEND_ORIGIN`, which defaults to `http://127.0.0.1:8000`. Start the backend on that origin before starting the frontend. A deployed frontend still requires its web server or gateway to route the same-origin `/v1` path to the backend.

In live mode, the Evidence submission screen renders the backend-provided `demoFiles` list. It lets a reviewer download and re-upload normal, point-in-time mismatch, required-field-missing, and hash-mismatch synthetic PDFs. The labels show the expected demo path, while the actual quality status always comes from the backend response. Older backends that only return `demoFile` remain supported.

When the backend returns `trustVerification`, the quality screen shows whether the signed Demo manifest was verified and which scopes were actually established. `SERVER_SIGNED_MANIFEST` confirms the synthetic document's integrity, manifest binding, and Demo issuing server only; it must not be presented as proof that a real financial institution issued the document.

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
