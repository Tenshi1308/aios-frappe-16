import assert from 'node:assert/strict';
import { createPinia, setActivePinia } from 'pinia';
import { useBranchesStore } from '../src/stores/branches';
import { useChatStore } from '../src/stores/chat';
import { useUiStore } from '../src/stores/ui';

type FetchCall = { url: string; method: string };

function setupStoresWithFetchMock(unreadCount: number, convId: string | null) {
  setActivePinia(createPinia());
  const ui = useUiStore();
  ui.agentOpen = true;
  const branches = useBranchesStore();
  branches.selectedKey = 'sales';
  const chat = useChatStore();
  chat.conversations.sales = [
    {
      id: 'CONV-OLD-1',
      branch: 'sales',
      title: 'Sesi Lama',
      is_pinned: false,
      is_archived: false,
      modified: '2026-11-19 10:00:00',
      creation: '2026-11-19 10:00:00',
      message_count: 2,
      last_message: 'Halo',
    },
  ];

  const calls: FetchCall[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    calls.push({ url, method });

    if (url.includes('get_unread_sales_insights')) {
      return new Response(
        JSON.stringify({ message: { unread_count: unreadCount, conversation_id: convId } }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.includes('list_conversations')) {
      return new Response(
        JSON.stringify({
          message: {
            conversations: [
              ...(convId
                ? [
                    {
                      id: convId,
                      branch: 'sales',
                      title: 'Ringkasan Proaktif Sales 2026-11-20',
                      is_pinned: false,
                      is_archived: false,
                      modified: '2026-11-20 10:00:00',
                      creation: '2026-11-20 10:00:00',
                      message_count: 1,
                      last_message: 'Ringkasan',
                    },
                  ]
                : []),
              ...chat.conversations.sales,
            ],
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.includes('get_conversation')) {
      return new Response(
        JSON.stringify({
          message: {
            conversation: { id: convId ?? 'CONV-OLD-1', branch: 'sales', title: 'Test' },
            messages: [{ id: 'm1', role: 'manager', worker_key: 'manager', content: 'Ringkasan' }],
            legacy_files: [],
          },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.includes('mark_sales_insights_read')) {
      return new Response(JSON.stringify({ message: { status: 'ok', marked: 1 } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(JSON.stringify({ message: {} }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  return { chat, calls };
}

async function runTests() {
  // 1. Polling saat panel terbuka di cabang Sales TIDAK boleh menghapus badge atau membuka sesi,
  //    dan harus memuat ulang daftar riwayat bila muncul conversation_id baru.
  {
    const { chat, calls } = setupStoresWithFetchMock(1, 'CONV-NEW-1');
    await chat.pollProactiveInsights();

    assert.equal(chat.proactiveUnreadCount, 1, 'Badge harus tetap 1 setelah polling');
    assert.equal(chat.proactiveConversationId, 'CONV-NEW-1');
    assert.equal(
      calls.some((c) => c.url.includes('mark_sales_insights_read')),
      false,
      'Polling tidak boleh memanggil mark_sales_insights_read',
    );
    assert.equal(
      calls.some((c) => c.url.includes('get_conversation')),
      false,
      'Polling tidak boleh otomatis membuka percakapan',
    );
    assert.equal(
      calls.some((c) => c.url.includes('list_conversations')),
      true,
      'Polling harus memuat ulang daftar percakapan saat ada conversation_id baru',
    );
    assert.equal(
      chat.conversations.sales.some((c) => c.id === 'CONV-NEW-1'),
      true,
      'Sesi baru harus langsung ada di daftar riwayat',
    );
  }

  // 2. Membuka sesi lama (bukan proactiveConversationId) tidak boleh menghapus badge.
  {
    const { chat, calls } = setupStoresWithFetchMock(1, 'CONV-NEW-1');
    await chat.pollProactiveInsights();
    await chat.openConversation('sales', 'CONV-OLD-1');

    assert.equal(chat.proactiveUnreadCount, 1, 'Membuka sesi lama tidak boleh menghapus badge');
    assert.equal(
      calls.some((c) => c.url.includes('mark_sales_insights_read')),
      false,
      'mark_sales_insights_read tidak boleh dipanggil untuk sesi lama',
    );
  }

  // 3. Membuka sesi ringkasan terbaru memuat isi sesi lalu menghapus badge.
  {
    const { chat, calls } = setupStoresWithFetchMock(1, 'CONV-NEW-1');
    await chat.pollProactiveInsights();
    await chat.openConversation('sales', 'CONV-NEW-1');

    const getIdx = calls.findIndex((c) => c.url.includes('get_conversation'));
    const markIdx = calls.findIndex((c) => c.url.includes('mark_sales_insights_read'));
    assert.ok(getIdx !== -1, 'get_conversation harus dipanggil');
    assert.ok(markIdx !== -1, 'mark_sales_insights_read harus dipanggil');
    assert.ok(markIdx > getIdx, 'mark_sales_insights_read harus dipanggil SETELAH get_conversation selesai');
    assert.equal(chat.proactiveUnreadCount, 0, 'Badge harus 0 setelah sesi ringkasan terbaru dibuka');
  }

  console.log('ALL_PROACTIVE_BADGE_TESTS_PASSED');
}

runTests().catch((err) => {
  console.error(err);
  process.exit(1);
});
