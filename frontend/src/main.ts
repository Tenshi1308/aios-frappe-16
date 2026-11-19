import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';
import { applyBrand, applyTheme, readCachedBrand, readCachedTheme } from './utils/theme';
import './styles/tokens.css';
import './styles/base.css';

applyTheme(readCachedTheme() ?? 'Automatic');
applyBrand(readCachedBrand() ?? 'finto');

createApp(App).use(createPinia()).use(router).mount('#app');
