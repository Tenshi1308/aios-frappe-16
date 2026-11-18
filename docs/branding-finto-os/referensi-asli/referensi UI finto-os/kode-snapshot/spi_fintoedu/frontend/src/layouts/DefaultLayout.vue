<template>
  <!-- Mode desktop: halaman tampil di dalam jendela; tanpa TopBar/sidebar/footer (disediakan shell desktop). -->
  <div v-if="win" class="desktop-window-page">
    <HubTabs :route-name="win.routeName.value" />
    <slot />
  </div>

  <template v-else>
    <TopBar />

    <LeftSideBar />

    <div class="page-wrapper">
      <div class="page-content">
        <div class="container-xxl">
          <HubTabs />
          <slot />
        </div>

        <Footer />
      </div>
    </div>

    <PageGuide />
    <!-- Panel kanan Tindak Lanjut (pengganti menu Tindak Lanjut) -->
    <ActionPane />
  </template>
</template>

<script setup lang="ts">
import { inject } from "vue";
import TopBar from "@/layouts/components/TopBar.vue";
import LeftSideBar from "@/layouts/components/LeftSideBar.vue";
import Footer from "@/layouts/components/Footer.vue";
import PageGuide from "@/features/onboarding/components/PageGuide.vue";
import HubTabs from "@/components/HubTabs/HubTabs.vue";
import ActionPane from "@/features/action-center/components/ActionPane.vue";
import { DESKTOP_WINDOW } from "@/features/desktop/context";

const win = inject(DESKTOP_WINDOW, null);
</script>
