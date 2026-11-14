# Deploy the minimal preview on Vercel

**Current state:** deployable **static** SiteGuard QR UI shell. There is no React build or FastAPI service at this milestone, and no database, QR attendance capture or payroll export functionality. It is intentionally a low-risk first deployment.

## What is deployed?

The public site serves `public/index.html`, `public/styles.css`, `public/app.js`, and `public/favicon.svg`. Overview, QR Timekeeping, Verification and Payroll Exports are navigable client-side preview panels; non-implemented capabilities are labeled as planned.

The app uses no third-party runtime/development packages, needs no environment variables and makes no API calls. The npm build script checks that Vercel assets and route panels exist and that the client JavaScript parses.

## Vercel settings

The repository includes **`vercel.json`**:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "outputDirectory": "public",
  "buildCommand": "npm run build"
}
```

`framework: null` selects Vercel **Other**; `public` is served unchanged, so there is no asset compilation step. Node.js **22+** is required for the repository's npm script and is declared in `package.json`.

| Setting | Value |
| --- | --- |
| Git repository | `ariz31/payroll` |
| Production branch | `main` |
| Project root | `./` (repository root) |
| Framework Preset | **Other** |
| Install command | `npm ci` (with committed lockfile, no package dependencies) |
| Build command | `npm run build` |
| Output directory | `public` |
| Environment variables | **None** for preview |
| SPA rewrites | Not needed; tabs use `#overview`, `#kiosk`, `#reviews`, `#exports` |

## Deploy from Vercel dashboard

1. Sign in at [Vercel](https://vercel.com), select **Add New → Project**.
2. Import **[ariz31/payroll](https://github.com/ariz31/payroll)** from GitHub; authorize access if required.
3. Keep the **Root Directory** at the repository root. Confirm **Framework Preset: Other**.
4. Confirm output directory **public** and build command **npm run build** (already committed to `vercel.json`).
5. No environment variables are needed. Select **Deploy**.
6. Open the generated `*.vercel.app` URL and verify that the Overview loads, tabs switch correctly, and static styles/icon load.
7. If the Git integration is enabled, later pushes to `main` trigger production builds. Review logs and deployment status in Vercel after each change.

**Important:** Repository changes do not by themselves create a hosted site. This is ready for the user to import; deployment is not asserted until Vercel returns a successful deployment.

## Local smoke check

```bash
npm ci
npm run build
npm test
python3 -m http.server 4173 --directory public
```

Then visit [http://localhost:4173](http://localhost:4173), and try all four sections. A static server is sufficient. `npm run build` is intentionally just a **validation step**, because static files are already in the output folder.

## First-deploy acceptance checklist

- [ ] Vercel deployment status **Ready** (not merely GitHub commit success).
- [ ] Root route `/` renders without 404.
- [ ] `/styles.css`, `/app.js` and `/favicon.svg` return 200.
- [ ] Hash routes `/#overview`, `/#kiosk`, `/#reviews`, `/#exports` display expected panels.
- [ ] Layout is usable on desktop and mobile.
- [ ] Browser console has no JS errors, blocked resources, or unexpected network requests.
- [ ] Clearly marked **preview-only** status; no implied real employee data, QR scanning or payroll calculations.
- [ ] Vercel project is connected to `main` for automatic future deploys.

## Troubleshooting

| Issue | Check |
| --- | --- |
| Build cannot locate files | Project root must be repository root; output directory `public` |
| Build reports missing asset or JS syntax | `npm run build` shows the asset/test that failed |
| Vercel serves repository instead of app | Framework must be Other; `vercel.json` must remain at repo root |
| Site 404 | Confirm deployment succeeded and `public/index.html` is committed |
| Blank panel / broken navigation | Confirm `/app.js` served correctly, check browser console and URL hash |
| Deployment cannot be started | Connect GitHub account/repository in Vercel; no Vercel project credentials are stored here |

## Next phase

Implement React 18 + TypeScript, FastAPI, PostgreSQL and immutable scan/review/export mechanics as described in the [PRD](../product/PRD.md) and [roadmap](../product/ROADMAP.md), replacing the static shell in a separately tested transition. Do not add live employee data before security and privacy decisions are approved.
