# Frontend Modular Redesign — Apple-style Restructure

**Date:** 2026-06-29
**Status:** draft

## Goal

Replace the current monolithic Migration Console (`App.tsx` — all features in one page)
with a modular, routed SPA covering **ScriptHub analysis** and **Database (projects/assets)**
domains only. Apply an Apple-inspired light-touch design system with rounded corners,
clean hierarchy, and subtle micro-interactions.

## Scope

### In scope

- Restructure `frontend/src/` from single-page to multi-route layout
- Two feature modules: **Database** (projects + assets) and **ScriptHub** (jobs + results)
- Dashboard as landing page with stats and quick-access cards
- Design system: colors, border-radius, typography, animations, spacing tokens
- Rail sidebar navigation with 3 icons (Dashboard, Database, ScriptHub)
- Reuse existing `shared/api/` modules (`client.ts`, `projects.ts`, `jobs.ts`)
- Reuse existing `shared/types/domain.ts`

### Out of scope

- Rewriting other analysis modules (heatmap, treemap, chord, PPT, statistical, etc.)
  — they remain accessible through the unified jobs bridge but do not get their own pages
- Backend changes (Flask stays as-is during Phase 1–2)
- Authentication / user management pages
- Internationalization

## Routes

| Path | Page | Description |
|------|------|-------------|
| `/` | Dashboard | Overview stats, project list, recent jobs |
| `/database` | Database | Project selector + asset browser |
| `/database/:projectId` | Database | Same page, specific project pre-selected |
| `/scripthub` | ScriptHub | Job submission, active job monitor, result viewer |

## Design System

### Colors

```css
:root {
  --bg-root:      #f5f5f7;    /* page background — iOS Settings-like */
  --bg-elevated:  #ffffff;    /* card surface */
  --bg-inset:     #e8e8ed;    /* sunken/inner background */

  --text-primary:   #1d1d1f;  /* primary text — near black */
  --text-secondary: #6e6e73;  /* secondary — labels, descriptions */
  --text-tertiary:  #aeaeb2;  /* placeholder, disabled */

  --accent:        #0071e3;   /* Apple Blue */
  --accent-hover:  #0077ed;
  --success:       #34c759;
  --warning:       #ff9500;
  --danger:        #ff3b30;

  --separator:  rgba(60,60,67,0.12);
  --shadow-sm:  0 1px 3px rgba(0,0,0,0.04);
  --shadow-md:  0 4px 12px rgba(0,0,0,0.06);
  --shadow-lg:  0 8px 30px rgba(0,0,0,0.08);
}
```

### Border Radius — Apple's layered philosophy

| Element | Radius | Notes |
|---------|--------|-------|
| Page card | `20px` | Dashboard widgets, job cards |
| Panel / Sheet | `16px` | Table wrappers, forms |
| Button / Input | `12px` | Interactive elements |
| Tag / Badge | `20px` (pill) | Status badges |
| Rail icon | `14px` | Nav icon container |

### Typography

```css
font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
             "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
```

- Headings: 600 weight, tight tracking (-0.02em)
- Body: 400 weight, 1.5 line-height
- Labels / captions: 500 weight, uppercase, 0.04em tracking

### Spacing Scale

`4px` base unit → 4, 8, 12, 16, 20, 24, 32, 40, 48

### Animations — Subtle micro-interactions

```css
/* Route transition */
.page-enter { opacity: 0; transform: translateY(8px); }
.page-enter-active { opacity: 1; transform: translateY(0); transition: 200ms ease-out; }

/* Card hover */
.card:hover { transform: scale(1.01); box-shadow: var(--shadow-md); transition: 150ms ease-out; }

/* Button press */
.btn:active { transform: scale(0.97); }

/* Skeleton loading */
@keyframes breathe { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

/* Transition durations */
--duration-fast: 120ms;    /* hover color change */
--duration-normal: 200ms;  /* route, card */
--duration-slow: 350ms;    /* sheet expand */
```

## Layout Shell (App.tsx)

```
┌─────────────────────────────────────────────┐
│ Rail │  <Outlet />                          │
│      │                                       │
│  72px│  Page content                         │
│  wide│  max-width 1200px                     │
│      │                                       │
└─────────────────────────────────────────────┘
```

Rail:
- Fixed 72px width, full height
- Background: `#1d1d1f` (near black, Apple-style)
- 3 icons stacked vertically with 12px gap, centered
- Icons: `LayoutDashboard` (Dashboard), `Database`, `FlaskConical` (ScriptHub)
- Active: `--accent` background pill, white icon
- Inactive: `#6e6e73` icon
- Brand mark at top: "IR" in 28px white, light separator below

## Pages

### Dashboard (`/`)

Sections (top to bottom):

1. **Welcome row** — "Immune Repertoire Platform" heading, date/subtitle
2. **Metric tiles** — 3 stat cards in a row (Projects, Results, Active Jobs), each with icon + large number + label
3. **Project cards** — grid of project cards (2 columns), each card shows: project name, institution, asset count badge, result count, click → navigates to `/database/:id`
4. **Recent Jobs** — slim list of last 5 jobs with status pill + module name + time ago

### Database (`/database`, `/database/:projectId`)

1. **Top bar** — back-to-projects button (if project selected), project name heading, asset type filter dropdown
2. **Tab row** — [Assets] [Results]
3. **Upload strip** — collapsible, shows only when Assets tab active: asset type select, file picker, replace checkbox, upload button
4. **Asset table** — columns: Name, Type, Size, Uploaded, Actions (Preview / Download). Pagination below.
5. **Results tab** — same asset table but filtered to `processed_result` type

No project selected state: show a centered "Select a project from the sidebar or Dashboard" prompt with a link back to `/`.

### ScriptHub (`/scripthub`)

Three panels stacked vertically:

1. **Submit Job** — card with: module dropdown, force-rerun checkbox, JSON payload textarea (monospace), submit button. Submit shows loading spinner, then success/error message.
2. **Active Jobs** — list of running/queued jobs auto-refreshed every 3s. Each row: module name, status badge (color-coded: blue=queued, orange=running, green=completed, red=failed), progress bar, elapsed time.
3. **Job Result** — shown when a completed job is selected. Output links (viewer.html, plot.png, table.csv etc.) and registered asset links (preview/download).

## Component Inventory

### New shared components

| Component | Props | Notes |
|-----------|-------|-------|
| `Rail` | `links: {icon, label, to}[]` | Sidebar nav |
| `PageHeader` | `title, subtitle?, breadcrumb?` | Consistent page top |
| `MetricCard` | `icon, value, label, trend?` | Stat display |
| `Card` | `children, onClick?, className?` | Rounded elevated container |
| `StatusBadge` | `status: string` | Color-coded pill |
| `ProgressBar` | `value: number, max?: number` | Thin rounded bar |
| `EmptyState` | `icon, title, description, action?` | Centered placeholder |
| `Skeleton` | `width?, height?, variant: 'text'\|'rect'\|'circle'` | Loading placeholder |
| `Sheet` | `open, onClose, children` | Bottom/center modal for preview |

### Reused / adapted from existing code

| Existing | Changes |
|----------|---------|
| `App.css` → `styles/tokens.css` + `styles/global.css` | Split tokens from layout |
| `client.ts` | No changes |
| `projects.ts` | No changes |
| `jobs.ts` | No changes |
| `domain.ts` | No changes |
| Asset upload logic (from App.tsx) | Extract to `features/assets/AssetUpload.tsx` |
| Job submit logic (from App.tsx) | Extract to `features/jobs/JobSubmitForm.tsx` |
| Job list + detail (from App.tsx) | Extract to `features/jobs/JobList.tsx` |
| Asset table (from App.tsx) | Extract to `features/assets/AssetTable.tsx` |
| Pagination (from App.tsx) | Extract to `shared/components/Pagination.tsx` |

## File Structure (target)

```
frontend/src/
├── main.tsx
├── vite-env.d.ts
├── app/
│   ├── App.tsx              # Shell: Rail + <Outlet />
│   ├── App.css              # Reset + rail + page wrapper + route transitions
│   ├── Dashboard.tsx        # / route
│   ├── Database.tsx         # /database route
│   └── ScriptHub.tsx        # /scripthub route
├── features/
│   ├── projects/
│   │   ├── ProjectCard.tsx
│   │   └── ProjectList.tsx
│   ├── assets/
│   │   ├── AssetTable.tsx
│   │   ├── AssetUpload.tsx
│   │   └── AssetPreview.tsx
│   ├── jobs/
│   │   ├── JobSubmitForm.tsx
│   │   ├── JobList.tsx
│   │   ├── JobRow.tsx
│   │   └── JobResultPanel.tsx
│   └── results/
│       └── ResultCard.tsx
├── shared/
│   ├── api/
│   │   ├── client.ts        # ✅ existing
│   │   ├── projects.ts      # ✅ existing
│   │   └── jobs.ts          # ✅ existing
│   ├── components/
│   │   ├── Rail.tsx
│   │   ├── PageHeader.tsx
│   │   ├── MetricCard.tsx
│   │   ├── Card.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── EmptyState.tsx
│   │   ├── Skeleton.tsx
│   │   ├── Pagination.tsx
│   │   ├── Tabs.tsx
│   │   └── Sheet.tsx
│   ├── hooks/
│   │   ├── useApi.ts
│   │   └── usePolling.ts
│   └── types/
│       └── domain.ts         # ✅ existing
└── styles/
    ├── tokens.css            # CSS custom properties
    └── global.css            # reset + typography + utilities
```

## Testing

- Existing Vite build (`npm run build`) must pass
- TypeScript strict mode (`npm run typecheck`) must pass
- Manual: all 3 pages render, route navigation works, API calls succeed through Vite proxy
- No regression: Flask backend unaffected

## Migration from current App.tsx

1. Extract shared components first (Card, StatusBadge, Pagination, etc.)
2. Create `App.tsx` shell with Rail + React Router `<Outlet />`
3. Create Dashboard page using extracted components
4. Create Database page (reuse AssetTable, AssetUpload from current code)
5. Create ScriptHub page (reuse JobSubmitForm, JobList, JobResultPanel)
6. Delete old monolithic `App.tsx`
7. Verify `npm run build` + `npm run typecheck`

**Rollback safety:** old `App.tsx` content can be restored from `6682c1a` if needed during migration.

## Future extension points

- Add new feature pages by adding a Rail icon + route
- Sheet component can host preview modals for CSV/PNG/HTML results
- usePolling hook can be upgraded to SSE when backend supports it (Phase 2)
- Tabs component reusable across Database and future analysis pages
