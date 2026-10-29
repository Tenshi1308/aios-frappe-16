import '../../frontend/src/styles/tokens.css';
import '../../frontend/src/styles/base.css';
import { createApp } from 'vue';
import App from './App.vue';
import { applyTheme, readCachedTheme } from '../../frontend/src/utils/theme';

applyTheme(readCachedTheme() ?? 'Automatic');

createApp(App).mount('#app');
