# Frontend Guidelines

Status: **development rules**. `frontend/AGENTS.md` applies throughout the frontend.
Read [Template Guidelines](TEMPLATE_GUIDELINES.md) before creating new UI.

## 1. Technology stack

Vue 3 Composition API, TypeScript, Vite, Rizz 1.1, Bootstrap 5, Bootstrap Vue Next,
Vue Router, Pinia, and Axios. Forms use Vuelidate. Charts use the existing ApexChart
wrapper. Date inputs use `FlatPicker.vue`; Link fields use `LinkAutocomplete.vue`.

Use `<script setup lang="ts">` for new components. Do not install a second UI, form,
state, chart, or HTTP framework when the current stack meets the need.

## 2. Feature-oriented organization

```text
features/<feature>/
├── pages/                 # route-level UI
├── components/            # domain-specific UI
├── api.ts                 # feature transport contract
├── types.ts               # inputs, DTOs, queries, options
└── styles.scss            # when custom styling is needed
```

Create additional folders only when needed. Features do not require a composable or
store. Pages may call feature APIs directly for lists/statistics/actions.

| Location                 | Appropriate contents                                       | Avoid                                     |
| ------------------------ | ---------------------------------------------------------- | ----------------------------------------- |
| Page                     | State/filters/pagination, UI composition, action handlers  | Raw endpoints, SQL/authorization rules    |
| Feature component        | Domain forms/details/widgets, local state                  | Direct prop mutation                      |
| `api.ts`                 | URLs, query mapping, response unwrapping, transport errors | UI dialogs or page state                  |
| `types.ts`               | Concrete DTO/input/query/option types                      | A generic type framework for one feature  |
| `helpers/http-client.ts` | Axios configuration and CSRF headers                       | Business decisions                        |
| `stores/`                | Session and genuinely global state                         | Copies of list data used by only one page |
| `components/`            | Generic components already shared across features          | Domain approval/finance logic             |

## 3. Reference implementations

List the project's reference pages here once they exist:

- `features/<entities>/pages/<Entity>ListPage.vue`: lists, filters, pagination,
  statistics, exports, row actions.
- `features/<entities>/components/<Entity>FormModal.vue`: validation, server options,
  uploads, form reset.

Follow their responsibility boundaries and interaction behavior. Small features do
not need charts, maps, exports, or modals unless users need them.

## 4. Routing and navigation

Register general routes in `src/router/routes.ts`, with lazy imports of feature pages.
Role Profile routes live in `src/router/profile-routes/<profile>.ts` and are
aggregated by that folder's `index.ts` before being included in the central route list:

```ts
{
  path: "/<area>/<entities>",
  name: "<area>.<entities>",
  meta: { title: "<Entity>", authRequired: true },
  component: () => import("@/features/<entities>/pages/<Entity>ListPage.vue"),
}
```

Role menu definitions are generated in `src/assets/data/menu-items.ts` from the
dashboard configuration and current session. Link menus using route names and the
existing parentKey structure.

The guard changes the title, checks `authRequired`, initializes the session, and
redirects Guest to `auth.sign-in` with `redirectedFrom`. It may also read
`systemManagerOnly` and `roleProfiles` metadata to keep users on their own landing
page. These checks are UX only: they do not carry business capabilities or record
scope and must never replace backend permission enforcement.

Use DefaultLayout for business pages. Do not add a second sidebar/topbar inside a
feature or render the shell twice through nested layouts.

## 5. List-page state model

| State                                                  | Purpose                                           |
| ------------------------------------------------------ | ------------------------------------------------- |
| `items`                                                | Data on the currently displayed page              |
| `search`                                               | Search input text                                 |
| `activeSearch`                                         | Last successfully loaded search, used for exports |
| `filters`                                              | Applied filters                                   |
| `filterDraft`                                          | Pending choices before Apply                      |
| `currentPage`, `pageLength`, `total`                   | Server pagination                                 |
| `sortBy`, `sortOrder`                                  | Server sorting                                    |
| `isLoading`, `error`                                   | List loading state                                |
| `statistics`, `isStatisticsLoading`, `statisticsError` | Separate summary state                            |
| `actionName`                                           | Record currently being processed                  |
| `isExporting`                                          | Prevents duplicate exports                        |
| `editingItem`, `formModalOpen`                         | Create/edit form context                          |

Use local `ref` and `reactive` for this state. Use Pinia only when multiple application
areas actually need the same state and its lifecycle is clear.

### Interaction rules

- New searches/filters reset pagination to page 1.
- Changing page size resets to page 1.
- Sorting runs on the server and shows a direction indicator.
- Pagination reloads the list; changing pages alone does not require new statistics.
- Search/filter actions load lists and statistics with the same filter parameters.
- Create/update reload lists/statistics; refresh options if their underlying data changed.
- Deleting the last row on a page other than page 1 moves back one page before reloading.
- Status changes require confirmation and refresh data after server success.
- Exports use applied filters, not unsent draft filter values.

Load lists/options/statistics with `Promise.all` on mount. Each loader handles its own
errors, so a failed chart does not have to hide a successfully loaded table.

## 6. Required UI states

| State                      | Expected behavior                                       |
| -------------------------- | ------------------------------------------------------- |
| Initial loading            | Clear spinner/loading indicator                         |
| Empty                      | Explain whether there is no data or no filter match     |
| Load failure               | Actionable message and a way to retry                   |
| Action in progress         | Disable the relevant action; prevent duplicate requests |
| Save success               | Close the form, refresh, show feedback                  |
| Save failure               | Keep the form open and retain input                     |
| Session/permission failure | Show the rejection; do not replace real data with mocks |
| Empty statistics           | Zero values/empty state; no division by zero            |
| Download failure           | Show an error instead of a corrupt XLSX file            |

Add request IDs or cancellation/stale-response guards to search-as-you-type and list
loaders when the workflow requires them, so older responses do not overwrite newer ones.

## 7. Modal form pattern

Props: `modelValue`, the edited record or `null`, and server `options`.
Events: `update:modelValue` and `saved` carrying the server-returned DTO.

```ts
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  saved: [item: <Entity>];
}>();
```

Form responsibilities:

1. Create empty state through a function such as `createEmptyForm()`.
2. On opening, reset state, errors, password/confirmation, and validation.
3. Copy record props into local state; do not mutate props.
4. Call `$validate()` before submission; show invalid-field messages near their inputs.
5. Construct an explicit payload matching the feature's `<Entity>Input` type.
6. Set loading during the request and prevent closing that could disrupt the operation.
7. Emit the saved DTO after success; the parent handles refresh and page feedback.
8. On error, retain input and display the feature error helper's message.

Edit modals fetch server details first. Do not assume list rows contain every field,
especially child tables.

### Validation

- Reuse Vuelidate and existing validators instead of introducing another library.
- Conditional required rules depend on explicit form flags.
- Passwords are required on create and optional on edit; confirmation is frontend-only.
- Select options (profiles, genders, time zones, linked records) come from the server,
  not scattered hard-coded arrays.
- Final duplicate and reference validation remains on the backend.
- Disabled inputs are not backend security; callers can alter payloads.

## 8. Standardized form controls

### 8.1 Link fields (searchable autocomplete)

- Any field representing a Link to another entity **must not** be a raw text input
  requiring users to type IDs (such as `XXX-2026-00001`).
- All Link fields **must** use the reusable `@/components/LinkAutocomplete.vue`
  component (or an equivalent searchable combobox).
- As the user types, show a filtered suggestion list with the record's primary label,
  a sublabel (for example its ID), and an optional contextual badge.
- Support click selection, clearing, and keyboard navigation (`ArrowDown`, `ArrowUp`,
  `Enter`, `Esc`).

### 8.1a Free-text fields with suggestions

- Native `<datalist>` / `list=""` is **prohibited**: browsers render it as a dark native
  balloon that does not match the page.
- When the value may be typed freely (e.g. a new Yayasan name in Data Migration) use
  `@/components/SuggestInput.vue` (`v-model`, `options: {value, label, sublabel?, badge?}[]`,
  events `select` and `enter`, optional `size="sm"`). Its dropdown uses the same styling as
  `LinkAutocomplete` (bordered, `bg-body`, primary-subtle highlight, keyboard navigation).

### 8.1b Alerts and dialogs

- bootstrap-vue-next 0.21 `BAlert` has **no `show` prop** (`modelValue` defaults to `false`):
  `<b-alert show>` renders nothing. Use `<b-alert :model-value="true">` (with `v-if` for conditions).
- Never use native `alert()` / `confirm()`; use SweetAlert2 (`Swal.fire`) like the rest of the app.

### 8.2 Date fields (unified FlatPicker)

- Native `<input type="date">` is **prohibited** to avoid inconsistent browser controls
  and date formatting.
- All date fields **must** use `@/components/FlatPicker.vue` with one shared
  configuration:

  ```typescript
  import { Indonesian } from "flatpickr/dist/l10n/id.js"; // match Indonesian
  import FlatPicker from "@/components/FlatPicker.vue";

  const dateOptions = {
    allowInput: true,
    altInput: true,
    altFormat: "d F Y",
    dateFormat: "Y-m-d",
    disableMobile: true,
    locale: Indonesian,
  };
  ```

- Display human-readable dates (for example `16 Oktober 2026`) while storing ISO
  `YYYY-MM-DD` values in the model.

## 9. APIs and TypeScript

- Put all business endpoints in `features/<feature>/api.ts`.
- Use the existing `HttpClient`; do not add `axios.create()` or raw `fetch` calls in pages.
- Keep input types separate from response DTOs when backend normalization changes their shape.
- UI parameters may use camelCase, but wire mappings must be explicit in the API module.
- Catch errors as `unknown`, then use the feature helper.
- Avoid `any` or type assertions used merely to conceal contract mismatches.
- Do not treat all response fields as writable form fields.
- Use server results after mutations, because records can be renamed.

## 10. Widget and file lifecycle

Widgets such as maps, charts, and pickers require cleanup:

- Wait for DOM elements before creating a widget (`nextTick`/modal events).
- Destroy widget instances when modals/pages unmount or their context disappears.
- Clear search timers and prevent older responses from overwriting newer queries.
- Use DOM `textContent` for server values inserted into widget popups.
- Large option lists use server pagination/`has_more`, not a download of every record.
- Revoke object URLs after exported files are used.
- Upload files before saving; report upload errors without submitting fabricated URLs.

Do not create global composables for behavior needed by only one component unless
lifecycle complexity provides a concrete reason.

## 11. Presentation, language, and accessibility

- Reuse Rizz classes and Bootstrap utilities before custom CSS.
- UI labels use Indonesian; profile names/wire enums follow the backend.
- Display dates according to local needs, but never shift date-only values to another day.
- Statuses must have text and color; do not rely on color alone.
- Forms need labels linked to input IDs, readable errors, and correct button types.
- Give icon buttons accessible names; password toggles use `aria-label`/`aria-pressed`.
- Check keyboard use, modal focus, narrow screens, and table overflow.
- Long header text (for example a user greeting) is width-limited with a `title`
  tooltip so it cannot push navigation off screen.
- Use Vue interpolation for user data; avoid `v-html` without a need and sanitization.
- Keep feature styles near the feature; shared admin styles remain generic to admin pages.
- **No gray for primary text (owner rule, 11 Nov 2026).** Button labels and primary list/table text (names, codes,
  values, amounts, status text, table headers) must not use `text-muted`/`text-secondary`/`outline-secondary`/
  `outline-light text-muted`. Use `outline-dark`/`outline-primary` for neutral buttons, `text-body` for link-style
  actions, `bg-light text-dark border` for neutral badges. Gray is only for auxiliary info (hints, an ID/email under a
  name, helper text, metadata timestamps, placeholders). Theme gray was darkened to `#64708a` (5.0:1 on white, WCAG AA):
  `$body-secondary-color` and `$secondary` in `src/assets/scss/config/_variables.scss`.
- **Tabs have visible separators.** Global rule `src/assets/scss/componets/_spi-tabs.scss` (imported in `app.scss`):
  `nav-pills` (`b-tabs pills`) get a framed container, bordered tabs with gaps, a padded active "balloon", and space
  before the content; `nav-tabs` get vertical separators. Do not restyle tabs per page.

### 11.y Currency inputs show thousand separators (11 Nov 2026)

Rupiah amount fields use `src/components/CurrencyInput.vue` (displays `1.100.000`, v-model stays a number), not
`<input type="number">`. Used in Harga SPP (price list grid, special price) and Buat Tagihan.

### 11.x Transaction rows are clickable (11 Nov 2026)

Every list row that represents a transaction document (Sales Invoice, Payment Entry, payment submission, journal,
payroll, payout, transfer) must open its detail when clicked: `class="tx-row" tabindex="0"` +
`tx.open(doctype, name)` from `useTransactionDetail()` and mount `<TransactionDetailModal>`. Action buttons stay, in a
cell with `@click.stop`. Spec: `docs/specs/TRANSACTION_DETAIL.md`.

## 12. Testing and review

```bash
cd frontend
npm run type-check
npm run build
```

`build` already calls `vue-tsc` before Vite. If one command provides the required
coverage, avoid unnecessary repetition. `build-only` does not check types. Do not report
npm `lint` or `test` scripts as passing unless they exist in `package.json`.

Run smoke tests appropriate to the change: login, loading/filtering/pagination,
invalid forms, save/edit, status/delete actions, exports, reopening modals, and
responsive layouts. Testing scope should follow risk; small copy/style changes do
not need a new testing framework. Record baseline failures separately from regressions.
