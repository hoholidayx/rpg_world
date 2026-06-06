<template>
  <div class="md-content" ref="containerRef" v-html="rendered"></div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'

const props = defineProps({
  content: {
    type: String,
    default: '',
  },
})

// ── Configure marked once ──────────────────────────────────────────

const renderer = {
  code({ text, lang }) {
    const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
    let highlighted
    try {
      highlighted = hljs.highlight(text, { language }).value
    } catch {
      highlighted = text
    }
    return `<pre><code class="hljs language-${language}">${highlighted}</code></pre>`
  },
}

marked.use({ renderer })

// ── Reactive render ───────────────────────────────────────────────

const containerRef = ref(null)

const rendered = computed(() => {
  if (!props.content) return ''
  return marked.parse(props.content)
})

// Apply syntax highlighting after DOM updates
watch(rendered, () => {
  nextTick(() => {
    if (!containerRef.value) return
    containerRef.value.querySelectorAll('pre code').forEach((block) => {
      hljs.highlightElement(block)
    })
  })
})
</script>

<style scoped>
/* ── Base ──────────────────────────────────────────────────── */
.md-content {
  line-height: 1.6;
  font-size: 14px;
  color: inherit;
}
.md-content > :first-child {
  margin-top: 0;
}
.md-content > :last-child {
  margin-bottom: 0;
}

/* ── Headings ──────────────────────────────────────────────── */
.md-content :deep(h1),
.md-content :deep(h2),
.md-content :deep(h3),
.md-content :deep(h4),
.md-content :deep(h5),
.md-content :deep(h6) {
  margin: 16px 0 8px;
  font-weight: 600;
  color: inherit;
  line-height: 1.3;
}
.md-content :deep(h1) { font-size: 1.5em; }
.md-content :deep(h2) { font-size: 1.3em; }
.md-content :deep(h3) { font-size: 1.15em; }
.md-content :deep(h4) { font-size: 1.05em; }

/* ── Paragraphs & text ─────────────────────────────────────── */
.md-content :deep(p) {
  margin: 8px 0;
}
.md-content :deep(strong) {
  font-weight: 600;
}
.md-content :deep(em) {
  font-style: italic;
}

/* ── Links ─────────────────────────────────────────────────── */
.md-content :deep(a) {
  color: #1677ff;
  text-decoration: none;
}
.md-content :deep(a:hover) {
  text-decoration: underline;
}

/* ── Lists ─────────────────────────────────────────────────── */
.md-content :deep(ul),
.md-content :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}
.md-content :deep(li) {
  margin: 2px 0;
}

/* ── Blockquotes ───────────────────────────────────────────── */
.md-content :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 4px solid var(--border-color);
  color: var(--text-secondary);
}
.md-content :deep(blockquote p) {
  margin: 4px 0;
}

/* ── Code blocks ───────────────────────────────────────────── */
.md-content :deep(pre) {
  margin: 10px 0;
  padding: 12px;
  border-radius: 6px;
  background: var(--hover-bg);
  border: 1px solid var(--border-color);
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.45;
}
.md-content :deep(pre code) {
  background: none;
  padding: 0;
  border: none;
  font-size: inherit;
  color: inherit;
}

/* ── Inline code ───────────────────────────────────────────── */
.md-content :deep(code) {
  background: var(--hover-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

/* ── Tables ────────────────────────────────────────────────── */
.md-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}
.md-content :deep(th),
.md-content :deep(td) {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
}
.md-content :deep(th) {
  background: var(--hover-bg);
  font-weight: 600;
}

/* ── Horizontal rules ──────────────────────────────────────── */
.md-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--border-color);
  margin: 16px 0;
}

/* ── Images ────────────────────────────────────────────────── */
.md-content :deep(img) {
  max-width: 100%;
  border-radius: 6px;
}

/* ── Task lists ────────────────────────────────────────────── */
.md-content :deep(input[type='checkbox']) {
  margin-right: 6px;
}
</style>
