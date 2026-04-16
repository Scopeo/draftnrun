import { fileURLToPath } from 'node:url'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { VueRouterAutoImports, getPascalCaseRouteName } from 'unplugin-vue-router'
import VueRouter from 'unplugin-vue-router/vite'
import { defineConfig } from 'vite'
import VueDevTools from 'vite-plugin-vue-devtools'
import Layouts from 'vite-plugin-vue-layouts'
import vuetify from 'vite-plugin-vuetify'
import svgLoader from 'vite-svg-loader'

export default defineConfig({
  plugins: [
    VueRouter({
      getRouteName: routeNode => {
        return getPascalCaseRouteName(routeNode)
          .replace(/([a-z\d])([A-Z])/g, '$1-$2')
          .toLowerCase()
      },
    }),
    vue(),
    VueDevTools(),
    vueJsx(),
    vuetify({
      autoImport: true,
      styles: {
        configFile: 'src/assets/styles/variables/_vuetify.scss',
      },
    }),
    Layouts({
      layoutsDirs: './src/layouts/',
    }),
    Components({
      dirs: ['src/components'],
      dts: true,
    }),
    AutoImport({
      imports: ['vue', VueRouterAutoImports, '@vueuse/core', 'pinia'],
      dirs: ['./src/composables/**', '!./src/composables/index.ts', './src/utils/**', './src/plugins/*/composables/**'],
      vueTemplate: true,
      ignore: ['useCookies', 'useStorage'],
    }),
    svgLoader(),
    ...(process.env.SENTRY_AUTH_TOKEN
      ? [
          sentryVitePlugin({
            org: process.env.SENTRY_ORG,
            project: process.env.SENTRY_PROJECT,
            authToken: process.env.SENTRY_AUTH_TOKEN,
          }),
        ]
      : []),
  ],
  define: { 'process.env': {} },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@images': fileURLToPath(new URL('./src/assets/images/', import.meta.url)),
      '@styles': fileURLToPath(new URL('./src/assets/styles/', import.meta.url)),
    },
  },
  build: {
    chunkSizeWarningLimit: 500,
    sourcemap: 'hidden',
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
          'vendor-vuetify': ['vuetify'],
          'vendor-sentry': ['@sentry/vue'],
          'vendor-supabase': ['@supabase/supabase-js'],
          'vendor-query': ['@tanstack/vue-query'],
          'vendor-tiptap': ['@tiptap/core', '@tiptap/vue-3', '@tiptap/starter-kit'],
          'vendor-vueflow': ['@vue-flow/core', '@vue-flow/background', '@vue-flow/controls', '@vue-flow/minimap'],
          'vendor-charts': ['chart.js', 'vue-chartjs'],
        },
      },
    },
  },
  optimizeDeps: {
    exclude: ['vuetify'],
    entries: ['./src/**/*.vue'],
    include: [
      'highlight.js/lib/core',
      'highlight.js/lib/languages/bash',
      'highlight.js/lib/languages/javascript',
      'highlight.js/lib/languages/python',
      'cronstrue',
    ],
  },
})
