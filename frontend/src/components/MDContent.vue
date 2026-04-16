<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { computed } from 'vue'
import { logger } from '@/utils/logger'

const props = defineProps<{
  content: string
}>()

// Language display names (module-level to avoid recreation on each render)
const LANG_NAMES: Record<string, string> = {
  js: 'JavaScript',
  javascript: 'JavaScript',
  ts: 'TypeScript',
  typescript: 'TypeScript',
  py: 'Python',
  python: 'Python',
  rb: 'Ruby',
  ruby: 'Ruby',
  java: 'Java',
  cpp: 'C++',
  c: 'C',
  cs: 'C#',
  go: 'Go',
  rust: 'Rust',
  php: 'PHP',
  swift: 'Swift',
  kotlin: 'Kotlin',
  sql: 'SQL',
  html: 'HTML',
  css: 'CSS',
  scss: 'SCSS',
  json: 'JSON',
  yaml: 'YAML',
  xml: 'XML',
  bash: 'Bash',
  shell: 'Shell',
  sh: 'Shell',
  text: 'Text',
  plaintext: 'Text',
}

const md = new MarkdownIt({
  // Never render raw HTML from model/user content
  html: false,
  linkify: true,
  typographer: true,
})

const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:'])

md.validateLink = (url: string) => {
  try {
    const parsed = new URL(url, window.location.origin)
    return SAFE_PROTOCOLS.has(parsed.protocol)
  } catch (error: unknown) {
    return false
  }
}

// Configure all links to open in new tabs
md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
  const aIndex = tokens[idx].attrIndex('target')

  if (aIndex < 0) tokens[idx].attrPush(['target', '_blank'])
  else tokens[idx].attrs![aIndex][1] = '_blank'

  const relIndex = tokens[idx].attrIndex('rel')
  if (relIndex < 0) tokens[idx].attrPush(['rel', 'noopener noreferrer'])
  else tokens[idx].attrs![relIndex][1] = 'noopener noreferrer'

  return self.renderToken(tokens, idx, options)
}

// Custom fence renderer to add copy button and language label
md.renderer.rules.fence = function (tokens, idx) {
  const token = tokens[idx]
  const lang = token.info.trim() || 'text'
  const code = token.content
  const displayLang = LANG_NAMES[lang] || lang.toUpperCase()

  let highlighted = ''
  if (lang && hljs.getLanguage(lang)) {
    try {
      highlighted = hljs.highlight(code, { language: lang }).value
    } catch (e) {
      logger.warn('Syntax highlight failed for language', lang, e)
      highlighted = md.utils.escapeHtml(code)
    }
  } else {
    try {
      highlighted = hljs.highlightAuto(code).value
    } catch (e) {
      logger.warn('Auto-highlight failed', { error: e })
      highlighted = md.utils.escapeHtml(code)
    }
  }

  return `<div class="code-block"><div class="code-header"><span class="code-lang">${displayLang}</span><button class="copy-btn" data-code="${md.utils.escapeHtml(code).replace(/"/g, '&quot;')}"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy</span></button></div><pre><code class="hljs language-${lang}">${highlighted}</code></pre></div>`
}

const renderedContent = computed(() => {
  let processedContent = props.content
  processedContent = processedContent.replace(/([^\n])\n(-{3,}|\*{3,}|_{3,})/g, '$1\n\n$2')

  return md.render(processedContent)
})

const handleClick = async (e: MouseEvent) => {
  const target = e.target as HTMLElement
  const btn = target.closest('.copy-btn') as HTMLButtonElement
  if (!btn) return

  const code = btn.dataset.code
    ?.replace(/&quot;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')

  if (!code) return

  await navigator.clipboard.writeText(code)
  btn.classList.add('copied')

  const span = btn.querySelector('span')
  if (span) span.textContent = 'Copied!'

  setTimeout(() => {
    btn.classList.remove('copied')
    if (span) span.textContent = 'Copy'
  }, 2000)
}
</script>

<template>
  <div class="markdown-content" @click="handleClick" v-html="renderedContent" />
</template>

<style lang="scss" scoped>
.markdown-content {
  font-family: inherit;
  line-height: 1.5;
  overflow-wrap: break-word;
  word-break: break-word;

  > :first-child {
    margin-top: 0 !important;
  }

  :deep(p) {
    margin-block: 0.5rem;
    white-space: pre-wrap;

    &:first-child {
      margin-top: 0;
    }

    &:empty {
      display: none;
    }
  }

  :deep(.code-block) {
    margin: 0;
    border-radius: 8px;
    overflow: hidden;
    background: #1f2937 !important;
    border: 1px solid #4b5563 !important;

    &:first-child {
      margin-top: 0;
    }
  }

  :deep(.code-header) {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    background: #374151 !important;
    border-bottom: 1px solid #4b5563 !important;
  }

  :deep(.code-lang) {
    font-size: 0.75rem;
    font-weight: 500;
    color: #a0a0a0 !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  :deep(.copy-btn) {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;
    border: none;
    background: transparent;
    color: #a0a0a0 !important;
    font-size: 0.75rem;
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.2s;

    &:hover {
      background: rgba(255, 255, 255, 0.1) !important;
      color: #ffffff !important;
    }

    &.copied {
      color: #4ec9b0 !important;
    }
  }

  :deep(pre) {
    margin: 0;
    padding: 1rem;
    overflow-x: auto;
    background: #1f2937 !important;

    code {
      font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
      font-size: 0.875rem;
      line-height: 1.6;
      background: transparent !important;
      padding: 0;
      color: #d4d4d4 !important;
    }
  }

  :deep(code) {
    border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.08);
    font-size: 0.875em;
    padding-block: 0.2rem;
    padding-inline: 0.4rem;
  }

  :deep(pre code) {
    padding: 0;
    background: none !important;
  }

  :deep(hr) {
    border: none;
    border-block-start: 1px solid rgba(var(--v-theme-on-surface), 0.12);
    margin-block: 1rem;
  }

  :deep(.code-block pre) {
    border-radius: 0 0 8px 8px;
  }

  /* VS2015 dark syntax highlighting - always dark for code blocks */
  :deep(.hljs-keyword) {
    color: #569cd6 !important;
  }
  :deep(.hljs-built_in) {
    color: #4ec9b0 !important;
  }
  :deep(.hljs-type) {
    color: #4ec9b0 !important;
  }
  :deep(.hljs-literal) {
    color: #569cd6 !important;
  }
  :deep(.hljs-number) {
    color: #b5cea8 !important;
  }
  :deep(.hljs-string) {
    color: #ce9178 !important;
  }
  :deep(.hljs-comment) {
    color: #6a9955 !important;
  }
  :deep(.hljs-function) {
    color: #dcdcaa !important;
  }
  :deep(.hljs-title) {
    color: #dcdcaa !important;
  }
  :deep(.hljs-params) {
    color: #9cdcfe !important;
  }
  :deep(.hljs-variable) {
    color: #9cdcfe !important;
  }
  :deep(.hljs-attr) {
    color: #9cdcfe !important;
  }
  :deep(.hljs-selector-class) {
    color: #d7ba7d !important;
  }
  :deep(.hljs-selector-id) {
    color: #d7ba7d !important;
  }
  :deep(.hljs-tag) {
    color: #569cd6 !important;
  }
  :deep(.hljs-name) {
    color: #569cd6 !important;
  }
  :deep(.hljs-attribute) {
    color: #9cdcfe !important;
  }
}
</style>
