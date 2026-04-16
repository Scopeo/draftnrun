import MarkdownIt from 'markdown-it'

const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:'])

function createSafeMarkdownParser() {
  const md = new MarkdownIt({
    html: false,
    linkify: true,
    typographer: true,
  })

  md.validateLink = (url: string) => {
    try {
      const parsed = new URL(url, 'https://draftnrun.com')
      return SAFE_PROTOCOLS.has(parsed.protocol)
    } catch (error: unknown) {
      return false
    }
  }

  md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
    const targetIndex = tokens[idx].attrIndex('target')
    if (targetIndex < 0) tokens[idx].attrPush(['target', '_blank'])
    else tokens[idx].attrs![targetIndex][1] = '_blank'

    const relIndex = tokens[idx].attrIndex('rel')
    if (relIndex < 0) tokens[idx].attrPush(['rel', 'noopener noreferrer'])
    else tokens[idx].attrs![relIndex][1] = 'noopener noreferrer'

    return self.renderToken(tokens, idx, options)
  }

  return md
}

const safeMarkdown = createSafeMarkdownParser()

export const parseMarkdown = (markdown: string): string => {
  return safeMarkdown.render(markdown)
}

/**
 * Parse markdown with custom CSS classes
 */
export const parseMarkdownWithClasses = (
  markdown: string,
  classes: {
    h1?: string
    h2?: string
    h3?: string
    p?: string
    ul?: string
    li?: string
    strong?: string
    em?: string
    link?: string
  } = {}
): string => {
  const defaultClasses = {
    h1: 'text-h3 font-weight-bold mb-4',
    h2: 'text-h5 font-weight-bold mb-3 mt-6',
    h3: 'text-h6 font-weight-bold mb-2 mt-4',
    p: 'mb-4',
    ul: 'mb-4',
    li: 'mb-1',
    strong: '',
    em: '',
    link: 'text-primary text-decoration-none',
  }

  const finalClasses = { ...defaultClasses, ...classes }

  let html = parseMarkdown(markdown)

  html = html
    .replace(/<h1>/g, `<h1 class="${finalClasses.h1}">`)
    .replace(/<h2>/g, `<h2 class="${finalClasses.h2}">`)
    .replace(/<h3>/g, `<h3 class="${finalClasses.h3}">`)
    .replace(/<p>/g, `<p class="${finalClasses.p}">`)
    .replace(/<ul>/g, `<ul class="${finalClasses.ul}">`)
    .replace(/<li>/g, `<li class="${finalClasses.li}">`)
    .replace(/<strong>/g, `<strong class="${finalClasses.strong}">`)
    .replace(/<em>/g, `<em class="${finalClasses.em}">`)
    .replace(/<a /g, `<a class="${finalClasses.link}" `)

  return html
}
