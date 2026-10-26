import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';
import { applyTheme, readCachedTheme } from './utils/theme';
import './styles/tokens.css';
import './styles/base.css';

applyTheme(readCachedTheme() ?? 'Automatic');

createApp(App).use(createPinia()).use(router).mount('#app');
