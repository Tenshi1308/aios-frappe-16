<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useBranchesStore } from '../../stores/branches';
import { useChatStore } from '../../stores/chat';
import { useSessionStore } from '../../stores/session';
import { useUiStore } from '../../stores/ui';
import { MAX_UPLOAD_BYTES, UPLOAD_EXTENSIONS } from '../../api/chat';
import { useWindowManager } from '../../composables/useWindowManager';
import { formatDurationMs } from '../../utils/format';
import type { ChatMessage } from '../../types';
import AgentStep from './AgentStep.vue';
import AppIcon from '../base/AppIcon.vue';
import RichText from '../base/RichText.vue';

const session = useSessionStore();
const branches = useBranchesStore();
const chat = useChatStore();
const ui = useUiStore();

const draft = ref('');
const fileInput = ref<HTMLInputElement | null>(null);
const threadEl = ref<HTMLElement | null>(null);
const uploading = ref(false);
const traceOpenId = ref<string | null>(null);

void branches.load();
void chat.loadPendingDrafts();

const branch = computed(() => branches.selected);
const branchKey = computed(() => branch.value?.key ?? '');
const messages = computed(() => chat.threadFor(branchKey.value));
const streaming = computed(() => chat.isStreaming(branchKey.value));
const files = computed(() => chat.files(branchKey.value));
const uploadPercent = computed(() => chat.uploadProgress[branchKey.value]);
const suggestions = computed(() => branches.suggestions(branchKey.value));
const conversations = computed(() => chat.conversations[branchKey.value] ?? []);

const firstName = computed(() => session.firstName);
const greeting = computed(() => {
  const name = firstName.value ? `Halo, ${firstName.value}.` : 'Halo.';
  const b = branch.value;
  if (!b) return name;
  const role = b.description ? ` ${b.description}` : '';
  return `${name}\nSaya membantu di bidang ${b.name}.${role}`;
});
const showGreeting = computed(() => messages.value.length === 0);
const showTyping = computed(
  () => streaming.value && messages.value.length > 0 && messages.value[messages.value.length - 1].text === '',
);
const canSend = computed(() => !!draft.value.trim() && !streaming.value);

function shortName(name: string) {
  return name.split(/\s+/)[0] ?? name;
}

function hasSummary(m: ChatMessage) {
  return !!(m.steps?.length || m.tokens || m.durationMs);
}

function summaryText(m: ChatMessage) {
  const parts = [`${m.steps?.length ?? 0} langkah`, `${m.tokens ?? 0} token`];
  if (m.durationMs) parts.push(formatDurationMs(m.durationMs));
  return parts.join(' · ');
}

const lastStepsLength = computed(() => messages.value[messages.value.length - 1]?.steps?.length ?? 0);
const lastArtifactsLength = computed(() => messages.value[messages.value.length - 1]?.artifacts?.length ?? 0);

// Tick 1 detik untuk durasi live (header Working for + durasi item berjalan).
const tick = ref(0);
let tickTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  tickTimer = setInterval(() => {
    tick.value += 1;
  }, 1000);
});
onUnmounted(() => {
  if (tickTimer) clearInterval(tickTimer);
});

function stepDurationText(m: ChatMessage, i: number): string {
  const times = m.stepTimes ?? [];
  const start = times[i];
  if (start === undefined) return '';
  const end = times[i + 1] ?? (m.live ? performance.now() : (m.startedAt ?? start) + (m.durationMs ?? 0));
  return formatDurationMs(Math.max(0, end - start));
}

function workingText(m: ChatMessage): string {
  void tick.value;
  if (!m.startedAt) return 'Working…';
  return `Working for ${formatDurationMs(performance.now() - m.startedAt)}`;
}

function openPendingDrafts() {
  useWindowManager().open('pending-drafts', 'Persetujuan Tertunda');
}

function fmtDate(value: string) {
  if (!value) return '';
  const d = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

watch(
  () => [
    messages.value.length,
    messages.value[messages.value.length - 1]?.text,
    messages.value[messages.value.length - 1]?.steps?.length,
    messages.value[messages.value.length - 1]?.artifacts?.length,
    chat.uploadProgress[branchKey.value],
  ],
  () => {
    void nextTick(() => {
      const el = threadEl.value;
      if (el) el.scrollTop = el.scrollHeight;
    });
  },
);

function switchBranch(key: string) {
  branches.selectBranch(key);
  chat.historyOpen[key] = false;
  void nextTick(() => {
    const el = threadEl.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function send(text?: string) {
  const value = (text ?? draft.value).trim();
  if (!value || streaming.value || !branchKey.value) return;
  draft.value = '';
  void chat.send(branchKey.value, value);
}

function pickFiles() {
  fileInput.value?.click();
}

async function onFilesPicked(e: Event) {
  const input = e.target as HTMLInputElement;
  const list = Array.from(input.files ?? []);
  input.value = '';
  if (!list.length || !branchKey.value) return;
  const rejected = list.find(
    (f) => !UPLOAD_EXTENSIONS.includes((f.name.split('.').pop() ?? '').toLowerCase()),
  );
  if (rejected) {
    ui.toast(`Format ${rejected.name} tidak didukung. Gunakan ${UPLOAD_EXTENSIONS.join(', ')}.`);
    return;
  }
  const oversize = list.find((f) => f.size > MAX_UPLOAD_BYTES);
  if (oversize) {
    ui.toast(`Ukuran ${oversize.name} melebihi batas 10 MB.`);
    return;
  }
  uploading.value = true;
  try {
    await chat.uploadFiles(branchKey.value, list);
  } catch (err) {
    ui.toast(err instanceof Error ? err.message : 'Unggahan gagal.');
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <aside class="agent-panel" aria-label="AI agents">
    <header class="ap-head">
      <div class="ap-title">
        <span v-if="branch" class="agent-dot lg" :data-branch="branch.key">{{ branch.name.charAt(0).toUpperCase() }}</span>
        <div v-if="branch">
          <b>{{ branch.name }}</b>
          <small>{{ branch.description || branch.tagline }}</small>
        </div>
        <div v-else><b>AI Agents</b><small>Memuat agent dari backend…</small></div>
      </div>
      <button
        v-if="chat.pendingDrafts.length"
        class="icon-btn approvals"
        :aria-label="`Persetujuan tertunda: ${chat.pendingDrafts.length}`"
        title="Persetujuan tertunda"
        @click="openPendingDrafts"
      >
        <AppIcon name="file" :size="18" />
        <span class="badge">{{ chat.pendingDrafts.length }}</span>
      </button>
      <button class="icon-btn" aria-label="Riwayat percakapan" @click="chat.toggleHistory(branchKey)">
        <AppIcon name="history" :size="18" />
      </button>
      <button class="icon-btn" aria-label="Tutup panel agent" @click="ui.closeAgent()">
        <AppIcon name="x" :size="18" />
      </button>
    </header>
    <nav class="ap-tabs" aria-label="Daftar agent">
      <button
        v-for="b in branches.branches"
        :key="b.key"
        :class="{ on: b.key === branchKey }"
        @click="switchBranch(b.key)"
      >
        <span class="agent-dot xs" :data-branch="b.key">{{ b.name.charAt(0).toUpperCase() }}</span>
        {{ shortName(b.name) }}
      </button>
    </nav>

    <div class="ap-history" v-if="chat.historyOpen[branchKey]">
      <div class="ap-history-head">
        <b>Riwayat percakapan</b>
        <button class="icon-btn" aria-label="Tutup riwayat" @click="chat.toggleHistory(branchKey)">
          <AppIcon name="x" :size="16" />
        </button>
      </div>
      <div class="ap-history-list">
        <button class="btn ghost wide" @click="chat.newConversation(branchKey)">
          <AppIcon name="plus" :size="15" /> Percakapan baru
        </button>
        <button
          v-for="c in conversations"
          :key="c.id"
          class="ap-history-item"
          :class="{ on: c.id === chat.currentConversation[branchKey] }"
          @click="chat.openConversation(branchKey, c.id)"
        >
          <b>{{ c.title }}</b>
          <small>{{ fmtDate(c.updatedAt) }}</small>
        </button>
        <div v-if="!chat.historyLoading[branchKey] && !conversations.length" class="empty-note">
          Belum ada percakapan di cabang ini.
        </div>
      </div>
    </div>

    <div ref="threadEl" class="ap-thread">
      <div v-if="showGreeting" class="msg agent">
        <div class="msg-who">
          <span v-if="branch" class="agent-dot xs" :data-branch="branch.key">{{ branch.name.charAt(0).toUpperCase() }}</span>
          {{ branch?.name ?? 'Agent' }}
        </div>
        <div class="bubble"><RichText :text="greeting" /></div>
      </div>
      <template v-for="m in messages" :key="m.id">
        <div class="msg" :class="m.role">
          <div v-if="m.role === 'agent'" class="msg-who">
            <span v-if="branch" class="agent-dot xs" :data-branch="branch.key">{{ branch.name.charAt(0).toUpperCase() }}</span>
            {{ branch?.name ?? 'Agent' }}
          </div>
          <div v-if="m.role === 'agent' && m.steps?.length" class="trace-block" :class="{ live: m.live }">
            <button class="trace-head" @click="traceOpenId = traceOpenId === m.id ? null : m.id">
              <span v-if="m.live" class="trace-live-dot" aria-hidden="true" />
              <b v-if="m.live">{{ workingText(m) }}</b>
              <template v-else>
                <b>Langkah agent · {{ m.steps.length }}</b>
                <span class="trace-summary">{{ summaryText(m) }}</span>
              </template>
              <span class="trace-toggle">{{ traceOpenId === m.id ? 'Sembunyikan' : 'Lihat detail' }}</span>
            </button>
            <div v-if="traceOpenId === m.id || m.live" class="trace-steps">
              <AgentStep
                v-for="(step, si) in m.steps"
                :key="si"
                :step="step"
                :default-open="!!m.live && si === (m.steps?.length ?? 0) - 1"
                :running="!!m.live && si === (m.steps?.length ?? 0) - 1"
                :duration-text="stepDurationText(m, si)"
              />
            </div>
          </div>
          <div class="bubble"><RichText :text="m.text" /></div>
          <div v-if="m.role === 'agent' && m.artifacts?.length" class="msg-artifacts">
            <span v-for="(a, ai) in m.artifacts" :key="ai" class="msg-artifact">
              {{ a.type === 'APPROVAL_CARD' ? `Persetujuan ${a.action_type}` : `Artefak ${a.type}` }}
            </span>
          </div>
        </div>
      </template>
      <div v-if="showTyping" class="msg agent">
        <div class="bubble typing"><i /><i /><i /></div>
      </div>
    </div>

    <div v-if="showGreeting && !streaming" class="ap-prompts">
      <button v-for="p in suggestions" :key="p" class="chip" @click="send(p)">{{ p }}</button>
    </div>

    <div v-if="files.length || uploadPercent !== undefined" class="ap-files">
      <div v-if="uploadPercent !== undefined" class="ap-file">
        <AppIcon name="paperclip" :size="13" />
        <span>Mengunggah… {{ uploadPercent }}%</span>
        <span class="bar"><i :style="{ width: uploadPercent + '%' }" /></span>
      </div>
      <div v-for="f in files" :key="f.id" class="ap-file">
        <AppIcon name="file" :size="13" />
        <span>{{ f.file_name }}</span>
        <button class="icon-btn" style="width: 20px; height: 20px" aria-label="Hapus lampiran" @click="chat.removeFile(branchKey, f.id)">
          <AppIcon name="x" :size="12" />
        </button>
      </div>
    </div>

    <form class="ap-input" @submit.prevent="send()">
      <textarea
        id="agent-input"
        v-model="draft"
        rows="1"
        :placeholder="'Kirim pesan ke ' + (branch?.name ?? 'agent')"
        aria-label="Pesan"
        @keydown.enter.exact.prevent="send()"
      />
      <button class="icon-btn" type="button" aria-label="Lampirkan berkas" :disabled="uploading" @click="pickFiles">
        <AppIcon name="paperclip" :size="17" />
      </button>
      <input
        ref="fileInput"
        type="file"
        :accept="UPLOAD_EXTENSIONS.map((e) => '.' + e).join(',')"
        multiple
        hidden
        aria-hidden="true"
        @change="onFilesPicked"
      />
      <button class="send" type="submit" :disabled="!canSend" aria-label="Kirim">
        <AppIcon name="send" :size="16" />
      </button>
    </form>
    <div class="ap-foot">AIOS · jawaban AI dapat keliru — periksa kembali angka penting.</div>
  </aside>
</template>
