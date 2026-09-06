const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

const shouldSkipTextNode = (node: Text) => {
    const parent = node.parentElement
    if (!parent) return true

    return Boolean(parent.closest([
        'script',
        'style',
        'textarea',
        '.katex',
        '.mermaid',
        '.markdown-search-highlight',
        '.copy-btn',
    ].join(', ')))
}

export const highlightRenderedMarkdownText = (html: string, searchWords: string[]): string => {
    const tokens = Array.from(new Set(searchWords.filter(Boolean)))
        .sort((left, right) => right.length - left.length)
    if (!html || tokens.length === 0) return html

    const pattern = new RegExp(tokens.map(escapeRegExp).join('|'), 'gi')
    const container = document.createElement('div')
    container.innerHTML = html

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT)
    const matchedNodes: Text[] = []
    let current: Node | null
    while ((current = walker.nextNode())) {
        const node = current as Text
        if (shouldSkipTextNode(node)) continue
        pattern.lastIndex = 0
        if (pattern.test(node.data)) matchedNodes.push(node)
    }

    matchedNodes.forEach((node) => {
        const fragment = document.createDocumentFragment()
        let cursor = 0
        pattern.lastIndex = 0

        for (const match of node.data.matchAll(pattern)) {
            const index = match.index
            const value = match[0]
            if (index > cursor) fragment.append(node.data.slice(cursor, index))

            const highlight = document.createElement('span')
            highlight.className = 'markdown-search-highlight bg-yellow-200 text-slate-900 rounded px-0.5 box-decoration-clone'
            highlight.textContent = value
            fragment.append(highlight)
            cursor = index + value.length
        }

        if (cursor < node.data.length) fragment.append(node.data.slice(cursor))
        node.replaceWith(fragment)
    })

    return container.innerHTML
}
