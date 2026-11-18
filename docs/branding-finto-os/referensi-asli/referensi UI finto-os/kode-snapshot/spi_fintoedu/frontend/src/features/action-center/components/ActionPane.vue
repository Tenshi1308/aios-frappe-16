<template>
  <template v-if="features.length">
    <!-- Tombol tepi kanan (saat panel tertutup) -->
    <button
      v-if="!pane.open"
      type="button"
      class="ap-edge"
      :class="{ 'ap-edge-desktop': desktop }"
      title="Buka panel Tindak Lanjut"
      aria-label="Buka panel Tindak Lanjut"
      data-guide="layout.action-pane"
      @click="pane.toggle()"
    >
      <i class="iconoir-warning-triangle"></i>
      <span class="ap-edge-label">Tindak Lanjut</span>
      <span v-if="pane.badge" class="ap-edge-badge">{{ pane.badge > 99 ? "99+" : pane.badge }}</span>
    </button>

    <transition name="ap-slide">
      <aside
        v-if="pane.open"
        class="ap"
        :class="{ 'ap-desktop': desktop, 'ap-overlay': !docked }"
        :style="{ width: `${ACTION_PANE_WIDTH}px` }"
        aria-label="Panel Tindak Lanjut"
      >
        <header class="ap-head">
          <div class="d-flex align-items-center gap-2 min-w-0">
            <i class="iconoir-warning-triangle text-warning"></i>
            <span class="fw-semibold">Tindak Lanjut</span>
          </div>
          <div class="d-flex align-items-center gap-1">
            <button type="button" class="ap-icon-btn" title="Muat ulang" aria-label="Muat ulang" :disabled="loading" @click="loadAll">
              <i class="iconoir-refresh" :class="{ 'ap-spin': loading }"></i>
            </button>
            <button type="button" class="ap-icon-btn" title="Buka halaman penuh" aria-label="Buka halaman penuh" @click="openFullPage">
              <i class="iconoir-open-new-window"></i>
            </button>
            <button type="button" class="ap-icon-btn" title="Tutup panel" aria-label="Tutup panel" @click="pane.close()">
              <i class="iconoir-xmark"></i>
            </button>
          </div>
        </header>

        <nav v-if="features.length > 1" class="ap-tabs" role="tablist">
          <button
            v-for="f in features"
            :key="f.id"
            type="button"
            role="tab"
            class="ap-tab"
            :class="{ active: tab === f.id }"
            :aria-selected="tab === f.id"
            @click="tab = f.id"
          >
            <i :class="f.icon" class="me-1"></i>{{ f.tabLabel || f.label }}
          </button>
        </nav>

        <div class="ap-body">
          <select
            v-if="companies.length > 1"
            v-model="company"
            class="form-select form-select-sm mb-2"
            aria-label="Unit / cabang"
            @change="loadAll"
          >
            <option v-for="c in companies" :key="c" :value="c">{{ c }}</option>
          </select>

          <div v-if="error" class="alert alert-danger py-2 small">{{ error }}</div>

          <!-- ── Perlu Tindakan ── -->
          <template v-if="tab === 'action-center'">
            <div v-if="loading && !actions" class="text-center py-4"><b-spinner small variant="primary" /></div>
            <template v-else-if="actions">
              <div class="ap-summary">
                <div v-for="p in actions.priorities" :key="p" class="ap-sum" :class="sumClass(p)">
                  <div class="ap-sum-n">{{ actions.summary[p] || 0 }}</div>
                  <div class="ap-sum-l">{{ p }}</div>
                </div>
              </div>
              <div v-for="c in visibleChecks" :key="c.key" class="ap-check">
                <button type="button" class="ap-check-head" :aria-expanded="!!openChecks[c.key]" @click="openChecks[c.key] = !openChecks[c.key]">
                  <span class="badge" :class="priorityBadge(c.priority)">{{ c.priority }}</span>
                  <span class="flex-grow-1 text-start small fw-semibold">{{ c.title }}</span>
                  <span class="badge bg-dark">{{ c.count }}</span>
                  <i :class="openChecks[c.key] ? 'iconoir-nav-arrow-up' : 'iconoir-nav-arrow-down'"></i>
                </button>
                <div v-if="openChecks[c.key]" class="ap-check-body">
                  <div class="small text-muted mb-2">{{ c.action }}</div>
                  <div v-for="(item, idx) in c.items" :key="idx" class="ap-item">
                    <div class="min-w-0 flex-grow-1">
                      <div class="small fw-semibold text-truncate">{{ item.student_name || item.submission || "-" }}</div>
                      <div class="fs-11 text-muted">
                        {{ item.detail }}<span v-if="item.amount"> · {{ rupiah(item.amount) }}</span>
                      </div>
                    </div>
                    <button v-if="item.applicant" type="button" class="btn btn-outline-dark btn-xs" @click="openLead(item.applicant, item.student_name)">Follow-up</button>
                    <button v-else-if="item.follow_up" type="button" class="btn btn-outline-dark btn-xs" @click="openFollowUp({ name: item.follow_up })">Catat</button>
                    <button
                      v-else-if="item.student && c.follow_up_type"
                      type="button"
                      class="btn btn-outline-dark btn-xs"
                      @click="openFollowUp({ student: item.student, studentName: item.student_name, type: c.follow_up_type, note: `${c.title}: ${item.detail || ''}` })"
                    >
                      Buat
                    </button>
                  </div>
                  <div class="d-flex justify-content-between align-items-center mt-1">
                    <small v-if="c.count > c.items.length" class="text-muted">{{ c.items.length }} dari {{ c.count }}</small>
                    <span v-else></span>
                    <button v-if="pageRoute(c.page)" type="button" class="btn btn-link btn-sm p-0" @click="goTo(c.page)">Buka halaman ›</button>
                  </div>
                </div>
              </div>
              <div v-if="!visibleChecks.length" class="text-center text-muted small py-4">Tidak ada yang perlu ditindaklanjuti. 🎉</div>
            </template>
          </template>

          <!-- ── Follow-up Murid ── -->
          <template v-else-if="tab === 'follow-ups'">
            <div class="d-flex align-items-center justify-content-between mb-2 gap-2">
              <b-form-checkbox v-model="mine" switch class="small" @change="loadFollowUps">Hanya tugas saya</b-form-checkbox>
              <button v-if="canEditFollowUp" type="button" class="btn btn-primary btn-xs" @click="openFollowUp({})">
                <i class="iconoir-plus me-1"></i>Buat
              </button>
            </div>
            <div v-if="loadingFollowUps" class="text-center py-4"><b-spinner small variant="primary" /></div>
            <template v-else>
              <button v-for="f in followUps" :key="f.name" type="button" class="ap-fu" @click="openFollowUp({ name: f.name })">
                <div class="d-flex justify-content-between gap-2">
                  <span class="small fw-semibold text-truncate">{{ f.student_name }}</span>
                  <span class="badge" :class="f.is_overdue ? 'bg-danger' : 'bg-warning text-dark'">{{ f.is_overdue ? "Terlambat" : f.status }}</span>
                </div>
                <div class="fs-11 text-muted">
                  {{ f.follow_up_type }} · {{ formatDate(f.due_date) }}<span v-if="f.assigned_to"> · {{ f.assigned_to }}</span>
                </div>
              </button>
              <div v-if="!followUps.length" class="text-center text-muted small py-4">Tidak ada follow-up terbuka.</div>
            </template>
          </template>
        </div>
      </aside>
    </transition>

    <FollowUpModal
      v-model="showFollowUp"
      :follow-up-name="followUpCtx.name ?? null"
      :student="followUpCtx.student"
      :student-name="followUpCtx.studentName"
      :follow-up-type="followUpCtx.type"
      :note="followUpCtx.note"
      source="Perlu Tindakan"
      @saved="loadAll"
    />
    <LeadFollowUpModal v-model="showLead" :applicant="lead.name" :applicant-name="lead.label" @saved="loadAll" />
  </template>
</template>

<script setup lang="ts">
/**
 * Panel kanan "Tindak Lanjut" untuk mode web & desktop (keputusan pemilik 6 Nov 2026), pengganti menu Tindak Lanjut.
 * - Layar lebar (≥ 1200px): panel MENEMPEL — konten utama (halaman web / jendela maksimal desktop) menyusut selebar
 *   panel, jadi form & tabel tidak pernah tertutup.
 * - Layar sempit: panel melayang; otomatis menutup saat sebuah form (modal) dibuka dari halaman utama.
 * Lebar yang dipakai diekspor ke CSS variable `--spi-pane-w` di <html>.
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { getPaneFeatures, roleRouteCandidates } from "@/assets/data/menu-catalog";
import { useAuthStore } from "@/stores/auth";
import { ACTION_PANE_WIDTH, useActionPaneStore } from "@/stores/actionPane";
import { extractErrorMessage } from "@/features/students/api";
import FollowUpModal from "@/features/follow-ups/components/FollowUpModal.vue";
import LeadFollowUpModal from "@/features/admissions/components/LeadFollowUpModal.vue";
import { getFollowUpOptions, listFollowUps, type FollowUp } from "@/features/follow-ups/api";
import { getActionCenter, type ActionCenter, type ActionPriority } from "../api";

const props = withDefaults(defineProps<{ desktop?: boolean }>(), { desktop: false });

const DOCK_QUERY = "(min-width: 1200px)";
const REFRESH_MS = 5 * 60 * 1000;

const auth = useAuthStore();
const pane = useActionPaneStore();
const router = useRouter();

const features = computed(() =>
  getPaneFeatures({ role: auth.effectiveRoleProfile, employmentCategory: auth.employment?.category ?? null }, auth.isSuperAdministrator),
);
const tab = ref<string>("action-center");
watch(
  features,
  (list) => {
    if (list.length && !list.some((f) => f.id === tab.value)) tab.value = list[0].id;
  },
  { immediate: true },
);

const docked = ref(true);
const company = ref("");
const companies = ref<string[]>([]);
const error = ref("");

// ── Perlu Tindakan
const actions = ref<ActionCenter | null>(null);
const loading = ref(false);
const openChecks = reactive<Record<string, boolean>>({});
const visibleChecks = computed(() => (actions.value?.checks || []).filter((c) => c.count > 0));

// ── Follow-up
const followUps = ref<FollowUp[]>([]);
const loadingFollowUps = ref(false);
const mine = ref(false);
const canEditFollowUp = ref(false);

// ── Modal (dibuka dari panel; tidak memicu tutup otomatis)
const showFollowUp = ref(false);
const followUpCtx = ref<{ name?: string | null; student?: string; studentName?: string; type?: string | null; note?: string }>({});
const showLead = ref(false);
const lead = ref<{ name: string | null; label: string }>({ name: null, label: "" });
const ownModalOpen = computed(() => showFollowUp.value || showLead.value);

const hasFeature = (id: string) => features.value.some((f) => f.id === id);

async function loadActions() {
  if (!hasFeature("action-center")) return;
  loading.value = true;
  try {
    const res = await getActionCenter(company.value || undefined);
    actions.value = res;
    company.value = res.company;
    companies.value = res.companies;
    pane.badge = (res.summary.MENDESAK || 0) + (res.summary["HARI INI"] || 0);
    for (const c of res.checks) if (openChecks[c.key] === undefined) openChecks[c.key] = false;
    error.value = "";
  } catch (err) {
    error.value = extractErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

async function loadFollowUps() {
  if (!hasFeature("follow-ups")) return;
  loadingFollowUps.value = true;
  try {
    const res = await listFollowUps({ company: company.value || undefined, status: "open", mine: mine.value ? 1 : 0 });
    followUps.value = res.follow_ups;
    if (!companies.value.length) {
      companies.value = res.companies;
      company.value = res.company;
    }
    if (!hasFeature("action-center")) pane.badge = res.follow_ups.filter((f) => f.is_overdue).length;
  } catch (err) {
    error.value = extractErrorMessage(err);
  } finally {
    loadingFollowUps.value = false;
  }
}

function loadAll() {
  return Promise.all([loadActions(), loadFollowUps()]);
}

function priorityBadge(p: ActionPriority) {
  return ({ MENDESAK: "bg-danger", "HARI INI": "bg-warning text-dark", "MINGGU INI": "bg-info", PANTAU: "bg-secondary" } as Record<string, string>)[p];
}
function sumClass(p: ActionPriority) {
  return ({ MENDESAK: "ap-sum-danger", "HARI INI": "ap-sum-warning", "MINGGU INI": "ap-sum-info", PANTAU: "ap-sum-muted" } as Record<string, string>)[p];
}
function rupiah(v: number) {
  return new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(v || 0);
}
function formatDate(v: string | null) {
  return v ? new Date(v).toLocaleDateString("id-ID", { day: "2-digit", month: "short" }) : "-";
}

function pageRoute(slug: string) {
  return roleRouteCandidates(slug, auth.effectiveRoleProfile).find((n) => router.hasRoute(n)) ?? null;
}
function navigate(name: string) {
  router.push({ name });
  if (!docked.value) pane.close();
}
function goTo(slug: string) {
  const name = pageRoute(slug);
  if (name) navigate(name);
}
function openFullPage() {
  const name = pageRoute(tab.value);
  if (name) navigate(name);
}
function openFollowUp(ctx: typeof followUpCtx.value) {
  followUpCtx.value = ctx;
  showFollowUp.value = true;
}
function openLead(name: string, label?: string) {
  lead.value = { name, label: label || name };
  showLead.value = true;
}

// ── Menempel vs melayang + CSS variable lebar panel
let mql: MediaQueryList | null = null;
const onMql = () => (docked.value = !!mql?.matches);
function applyWidthVar() {
  const reserve = features.value.length && pane.open && docked.value ? ACTION_PANE_WIDTH : 0;
  document.documentElement.style.setProperty("--spi-pane-w", `${reserve}px`);
}
watch([() => pane.open, docked, features], applyWidthVar);

// Layar sempit: modal dari halaman utama dibuka → panel ditutup agar form terlihat penuh.
let observer: MutationObserver | null = null;
function watchModals() {
  observer = new MutationObserver(() => {
    if (docked.value || !pane.open || ownModalOpen.value) return;
    if (document.querySelector(".modal.show")) pane.close();
  });
  observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ["class"], childList: true });
}

let timer: ReturnType<typeof setInterval> | undefined;
onMounted(async () => {
  mql = window.matchMedia(DOCK_QUERY);
  onMql();
  mql.addEventListener("change", onMql);
  applyWidthVar();
  watchModals();
  if (!features.value.length) return;
  if (hasFeature("follow-ups")) {
    getFollowUpOptions()
      .then((o) => (canEditFollowUp.value = o.can_edit))
      .catch(() => undefined);
  }
  await loadAll();
  timer = setInterval(() => {
    if (pane.open || !document.hidden) loadAll();
  }, REFRESH_MS);
});
watch(
  () => pane.open,
  (v) => {
    if (v && features.value.length) loadAll();
  },
);
watch(() => auth.effectiveRoleProfile, () => features.value.length && loadAll());

onBeforeUnmount(() => {
  mql?.removeEventListener("change", onMql);
  observer?.disconnect();
  clearInterval(timer);
  document.documentElement.style.setProperty("--spi-pane-w", "0px");
});

defineExpose({ reload: loadAll, desktop: props.desktop });
</script>

<style scoped>
.ap {
  position: fixed;
  top: var(--bs-topbar-height, 70px);
  right: 0;
  bottom: 0;
  z-index: 1010; /* di bawah modal (1050+) sehingga form tidak pernah tertutup panel */
  display: flex;
  flex-direction: column;
  background: var(--bs-body-bg);
  border-left: 1px solid var(--bs-border-color);
  box-shadow: -6px 0 18px rgba(15, 23, 42, 0.06);
}
.ap.ap-overlay {
  box-shadow: -10px 0 30px rgba(15, 23, 42, 0.25);
  max-width: calc(100vw - 24px);
}
.ap.ap-desktop {
  position: absolute;
  top: 0;
  bottom: var(--os-taskbar-h, 48px);
  z-index: 9000; /* di atas jendela, di bawah taskbar/menu Start */
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(10px);
}
.ap-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--bs-border-color);
}
.ap-icon-btn {
  border: 0;
  background: transparent;
  width: 30px;
  height: 30px;
  border-radius: 6px;
  color: var(--bs-secondary-color);
}
.ap-icon-btn:hover {
  background: var(--bs-tertiary-bg);
  color: var(--bs-body-color);
}
.ap-spin {
  display: inline-block;
  animation: ap-spin 0.9s linear infinite;
}
.ap-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px 0;
}
.ap-tab {
  flex: 1;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  padding: 6px 4px;
  font-size: 13px;
  color: var(--bs-secondary-color);
}
.ap-tab.active {
  color: var(--bs-primary);
  border-bottom-color: var(--bs-primary);
  font-weight: 600;
}
.ap-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.ap-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
  margin-bottom: 12px;
}
.ap-sum {
  border-radius: 8px;
  padding: 6px 4px;
  text-align: center;
}
.ap-sum-n {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.1;
}
.ap-sum-l {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.ap-sum-danger {
  background: var(--bs-danger-bg-subtle);
  color: var(--bs-danger);
}
.ap-sum-warning {
  background: var(--bs-warning-bg-subtle);
  color: var(--bs-warning-text-emphasis);
}
.ap-sum-info {
  background: var(--bs-info-bg-subtle);
  color: var(--bs-info-text-emphasis);
}
.ap-sum-muted {
  background: var(--bs-tertiary-bg);
  color: var(--bs-secondary-color);
}
.ap-check {
  border: 1px solid var(--bs-border-color);
  border-radius: 8px;
  margin-bottom: 6px;
  overflow: hidden;
}
.ap-check-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  padding: 8px 10px;
}
.ap-check-head .badge {
  font-size: 11px;
}
.ap-check-body {
  border-top: 1px solid var(--bs-border-color);
  padding: 8px 10px;
}
.ap-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px dashed var(--bs-border-color);
}
.ap-item:last-of-type {
  border-bottom: 0;
}
.btn-xs {
  padding: 2px 8px;
  font-size: 11px;
  white-space: nowrap;
}
.ap-fu {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid var(--bs-border-color);
  border-radius: 8px;
  background: transparent;
  padding: 8px 10px;
  margin-bottom: 6px;
}
.ap-fu:hover {
  background: var(--bs-tertiary-bg);
}

/* Tombol tepi kanan */
.ap-edge {
  position: fixed;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  z-index: 1010;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 6px;
  border: 1px solid var(--bs-border-color);
  border-right: 0;
  border-radius: 10px 0 0 10px;
  background: var(--bs-body-bg);
  color: var(--bs-body-color);
  box-shadow: -4px 0 14px rgba(15, 23, 42, 0.12);
}
.ap-edge:hover {
  color: var(--bs-primary);
}
.ap-edge-desktop {
  position: absolute;
  z-index: 9000;
}
.ap-edge-label {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  font-size: 12px;
  font-weight: 600;
}
.ap-edge-badge {
  min-width: 20px;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--bs-danger);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.ap-slide-enter-active,
.ap-slide-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.ap-slide-enter-from,
.ap-slide-leave-to {
  transform: translateX(24px);
  opacity: 0;
}
@keyframes ap-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .ap-slide-enter-active,
  .ap-slide-leave-active {
    transition: none;
  }
}
</style>
