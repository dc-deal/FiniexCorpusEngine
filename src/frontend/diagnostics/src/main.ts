import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'katex/dist/katex.min.css'
import '@/styles/tokens.css'
import '@/styles/base.css'
import '@/styles/menu.css'
import App from '@/App.vue'
import { router } from '@/router'

createApp(App).use(createPinia()).use(router).mount('#app')
