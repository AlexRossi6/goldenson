import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import type { Block } from '../../types/api'

type BlockPayload = {
  version: number
  content: Record<string, unknown>
}

type InlineEditableBlockProps = {
  block: Block
  onCreateBlockAfter: (content: Record<string, unknown>) => Promise<Block>
  onUpdateBlock: (blockId: string, payload: BlockPayload) => Promise<void>
  onDeleteBlock: (block: Block) => Promise<void>
}

type TodoItem = { id: string; text: string; completed: boolean }
type TodoContent = { title: string; items: TodoItem[] }

function parseMarkdownLine(raw: string): { level: number; content: string } {
  const match = raw.match(/^(#{1,6})\s(.*)$/)
  return match ? { level: match[1].length, content: match[2] } : { level: 0, content: raw }
}

function makeMarkdownLine(level: number, content: string): string {
  return level > 0 ? `${'#'.repeat(level)} ${content}` : content
}

function normalizeTodoContent(content: Record<string, unknown>): TodoContent {
  if (Array.isArray(content.items)) {
    return {
      title: typeof content.title === 'string' ? content.title : '',
      items: content.items as TodoItem[],
    }
  }
  return {
    title: '',
    items: [{ id: 'legacy', text: typeof content.text === 'string' ? content.text : '', completed: content.checked === true }],
  }
}

function generateId(): string {
  return `item-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function serializeEditable(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return (node.textContent ?? '').replaceAll('\u200b', '')
  if (node instanceof HTMLBRElement) return '\n'
  return Array.from(node.childNodes, serializeEditable).join('')
}

function editableText(element: HTMLElement): string {
  return serializeEditable(element)
}

function getCaretOffset(element: HTMLElement): number {
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0 || !element.contains(selection.anchorNode)) return editableText(element).length
  const range = selection.getRangeAt(0).cloneRange()
  range.selectNodeContents(element)
  range.setEnd(selection.anchorNode as Node, selection.anchorOffset)
  return serializeEditable(range.cloneContents()).length
}

function focusAt(element: HTMLElement | null, offset: number): void {
  if (!element) return
  element.focus()
  const selection = window.getSelection()
  const range = document.createRange()
  const node = element.firstChild || element
  range.setStart(node, Math.min(offset, node.textContent?.length ?? 0))
  range.collapse(true)
  selection?.removeAllRanges()
  selection?.addRange(range)
}

export function InlineEditableBlock({ block, onCreateBlockAfter, onUpdateBlock, onDeleteBlock }: InlineEditableBlockProps) {
  const initialText = block.type === 'code'
    ? typeof block.content.code === 'string' ? block.content.code : ''
    : typeof block.content.text === 'string' ? block.content.text : ''
  const [text, setText] = useState(initialText)
  const [todoContent, setTodoContent] = useState<TodoContent>(() => normalizeTodoContent(block.content))
  const [busy, setBusy] = useState(false)
  const markdownLineRefs = useRef<Array<HTMLDivElement | null>>([])
  const todoItemRefs = useRef<Array<HTMLDivElement | null>>([])
  const paragraphRef = useRef<HTMLDivElement | null>(null)
  const handledEnterRef = useRef(false)
  const textRef = useRef(initialText)
  const todoRef = useRef(todoContent)

  const save = async (content: Record<string, unknown>) => {
    if (JSON.stringify(content) === JSON.stringify(block.content)) return
    setBusy(true)
    try {
      await onUpdateBlock(block.id, { version: block.version, content })
    } finally {
      setBusy(false)
    }
  }

  const persist = (content: Record<string, unknown>) => {
    void save(content).catch(() => undefined)
  }

  const updateText = (lines: string[], shouldRender = true) => {
    const nextText = lines.join('\n')
    textRef.current = nextText
    if (shouldRender) setText(nextText)
  }

  const updateTodo = (next: TodoContent, shouldPersist = false) => {
    todoRef.current = next
    setTodoContent(next)
    if (shouldPersist) persist(next)
  }

  const handleMarkdownInput = (index: number, element: HTMLDivElement) => {
    const lines = textRef.current.split('\n')
    const current = parseMarkdownLine(lines[index] ?? '')
    const visibleText = editableText(element)
    const typedHeading = block.type === 'paragraph' ? parseMarkdownLine(visibleText) : null
    lines[index] = block.type === 'heading' ? visibleText : typedHeading?.level ? visibleText : makeMarkdownLine(current.level, visibleText)
    if (typedHeading?.level) element.textContent = typedHeading.content
    updateText(lines, Boolean(typedHeading?.level))
    if (typedHeading?.level) {
      window.setTimeout(() => focusAt(markdownLineRefs.current[index], typedHeading.content.length), 0)
    }
  }

  const handleParagraphInput = (element: HTMLDivElement) => {
    const selection = window.getSelection()
    const anchor = selection?.anchorNode
    if (anchor?.nodeType === Node.TEXT_NODE && anchor.textContent?.includes('\u200b')) {
      const offset = selection?.anchorOffset ?? 0
      const removedBeforeCaret = anchor.textContent.slice(0, offset).split('\u200b').length - 1
      anchor.textContent = anchor.textContent.replaceAll('\u200b', '')
      const range = document.createRange()
      range.setStart(anchor, Math.max(0, offset - removedBeforeCaret))
      range.collapse(true)
      selection?.removeAllRanges()
      selection?.addRange(range)
    }
    const visibleText = editableText(element)
    const current = parseMarkdownLine(textRef.current)
    const typedHeading = parseMarkdownLine(visibleText)
    if (typedHeading.level) {
      textRef.current = visibleText
      element.textContent = typedHeading.content
      setText(visibleText)
      window.setTimeout(() => focusAt(paragraphRef.current, typedHeading.content.length), 0)
    } else {
      textRef.current = makeMarkdownLine(current.level, visibleText)
    }
  }

  const insertParagraphLineBreak = () => {
    const element = paragraphRef.current
    if (!element) return
    const caret = getCaretOffset(element)
    const current = textRef.current
    textRef.current = `${current.slice(0, caret)}\n${current.slice(caret)}`

    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0 || !element.contains(selection.anchorNode)) {
      element.textContent = textRef.current
      focusAt(element, caret + 1)
      return
    }
    const range = selection.getRangeAt(0)
    range.deleteContents()
    const newline = document.createElement('br')
    range.insertNode(newline)
    const caretNode = document.createTextNode('\u200b')
    newline.after(caretNode)
    range.setStart(caretNode, 1)
    range.collapse(true)
    selection.removeAllRanges()
    selection.addRange(range)
  }

  const finishParagraph = () => {
    const caret = getCaretOffset(paragraphRef.current as HTMLDivElement)
    const current = textRef.current
    const finished = current.slice(0, caret)
    const remainder = current.slice(caret)
    updateText([finished])
    void save({ ...block.content, text: finished })
      .then(() => onCreateBlockAfter({ text: remainder }))
      .then((created) => {
        window.setTimeout(() => {
          const next = document.querySelector<HTMLElement>(`[data-block-id="${created.id}"] [contenteditable="true"]`)
          focusAt(next, 0)
        }, 0)
      })
      .catch(() => undefined)
  }

  const handleParagraphEnter = (shiftKey: boolean) => {
    if (shiftKey) insertParagraphLineBreak()
    else finishParagraph()
  }

  const handleParagraphBeforeInput = (event: FormEvent<HTMLDivElement>) => {
    const inputType = (event.nativeEvent as InputEvent).inputType
    if (inputType !== 'insertLineBreak' && inputType !== 'insertParagraph') return
    event.preventDefault()
    if (handledEnterRef.current) return
    handleParagraphEnter(inputType === 'insertLineBreak')
  }

  const handleParagraphKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter') return
    event.preventDefault()
    handledEnterRef.current = true
    window.setTimeout(() => { handledEnterRef.current = false }, 0)
    handleParagraphEnter(event.shiftKey)
  }

  const handleMarkdownKeyDown = (event: KeyboardEvent<HTMLDivElement>, index: number) => {
    const lines = textRef.current.split('\n')
    const parsed = parseMarkdownLine(lines[index] ?? '')
    const caret = getCaretOffset(event.currentTarget)

    if (event.key === 'Enter') {
      event.preventDefault()
      if (event.shiftKey && block.type === 'paragraph') {
        lines[index] = `${parsed.content.slice(0, caret)}\n${parsed.content.slice(caret)}`
        updateText(lines)
        window.setTimeout(() => focusAt(markdownLineRefs.current[index], caret + 1), 0)
        return
      }
      lines.splice(index, 1, makeMarkdownLine(parsed.level, parsed.content.slice(0, caret)), parsed.content.slice(caret))
      updateText(lines)
      window.setTimeout(() => focusAt(markdownLineRefs.current[index + 1], 0), 0)
      return
    }

    if (event.key === 'Backspace' && caret === 0) {
      if (parsed.level > 0) {
        event.preventDefault()
        lines[index] = makeMarkdownLine(parsed.level - 1, parsed.content)
        updateText(lines)
        window.setTimeout(() => focusAt(markdownLineRefs.current[index], 0), 0)
      } else if (index > 0) {
        event.preventDefault()
        const previous = parseMarkdownLine(lines[index - 1])
        const previousLength = previous.content.length
        lines.splice(index - 1, 2, makeMarkdownLine(previous.level, previous.content + parsed.content))
        updateText(lines)
        window.setTimeout(() => focusAt(markdownLineRefs.current[index - 1], previousLength), 0)
      }
    }
  }

  const handleTodoItemKeyDown = (event: KeyboardEvent<HTMLDivElement>, index: number) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      const items = [...todoRef.current.items]
      items.splice(index + 1, 0, { id: generateId(), text: '', completed: false })
      updateTodo({ ...todoRef.current, items }, true)
      window.setTimeout(() => focusAt(todoItemRefs.current[index + 1], 0), 0)
      return
    }

    if (event.key === 'Backspace' && editableText(event.currentTarget) === '' && todoRef.current.items.length > 1) {
      event.preventDefault()
      const items = todoRef.current.items.filter((_, itemIndex) => itemIndex !== index)
      updateTodo({ ...todoRef.current, items }, true)
      const previousIndex = Math.max(0, index - 1)
      window.setTimeout(() => focusAt(todoItemRefs.current[previousIndex], items[previousIndex]?.text.length ?? 0), 0)
    }
  }

  const paragraph = parseMarkdownLine(text)

  return (
    <li className={`block-card block-${block.type}`} data-block-id={block.id}>
      <div className="block-context-actions">
        <button type="button" className="block-delete text-button danger-link" aria-label={`Delete ${block.type} block`} onClick={() => void onDeleteBlock(block)} disabled={busy}>Delete</button>
      </div>
      <div className="block-content" aria-busy={busy}>
        {block.type === 'todo' ? (
          <div className="todo-block">
            <div
              className="inline-text todo-title"
              contentEditable={!busy}
              suppressContentEditableWarning
              role="textbox"
              aria-label="Todo title"
              data-placeholder="Task list title..."
              onInput={(event) => {
                todoRef.current = { ...todoRef.current, title: editableText(event.currentTarget) }
              }}
              onBlur={() => persist(todoRef.current)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  focusAt(todoItemRefs.current[0], 0)
                }
              }}
            >
              {todoContent.title}
            </div>
            {todoContent.items.map((item, index) => (
              <div key={item.id} className="todo-row">
                <input
                  type="checkbox"
                  aria-label={`Mark ${item.text || 'task'} complete`}
                  checked={item.completed}
                  disabled={busy}
                  onChange={() => {
                    const items = todoRef.current.items.map((current) => current.id === item.id ? { ...current, completed: !current.completed } : current)
                    updateTodo({ ...todoRef.current, items }, true)
                  }}
                />
                <div
                  ref={(element) => { todoItemRefs.current[index] = element }}
                  className={`inline-text todo-item${item.completed ? ' is-completed' : ''}`}
                  contentEditable={!busy}
                  suppressContentEditableWarning
                  role="textbox"
                  aria-label={`Todo item ${index + 1}`}
                  data-placeholder="What needs to be done?"
                  onInput={(event) => {
                    const items = todoRef.current.items.map((current) => current.id === item.id ? { ...current, text: editableText(event.currentTarget) } : current)
                    todoRef.current = { ...todoRef.current, items }
                  }}
                  onBlur={() => persist(todoRef.current)}
                  onKeyDown={(event) => handleTodoItemKeyDown(event, index)}
                >
                  {item.text}
                </div>
              </div>
            ))}
          </div>
        ) : block.type === 'code' ? (
          <pre className="inline-code-shell">
            <code
              className="inline-code"
              contentEditable={!busy}
              suppressContentEditableWarning
              role="textbox"
              aria-label="Code content"
              aria-multiline="true"
              data-placeholder="Write code..."
              onInput={(event) => {
                textRef.current = editableText(event.currentTarget)
              }}
              onBlur={() => persist({ ...block.content, code: textRef.current })}
            >
              {text}
            </code>
          </pre>
        ) : block.type === 'paragraph' ? (
          <div className="inline-document" aria-label="Paragraph content">
            <div
              ref={paragraphRef}
              className={`inline-text markdown-level-${paragraph.level}`}
              contentEditable={!busy}
              suppressContentEditableWarning
              role="textbox"
              aria-label="Paragraph content"
              aria-multiline="true"
              data-placeholder="Start writing..."
              onInput={(event) => handleParagraphInput(event.currentTarget)}
              onBeforeInput={handleParagraphBeforeInput}
              onKeyDown={handleParagraphKeyDown}
              onBlur={() => persist({ ...block.content, text: textRef.current })}
            >
              {paragraph.content}
            </div>
          </div>
        ) : (
          <div className="inline-document" aria-label={block.type === 'paragraph' ? 'Paragraph content' : 'Heading content'}>
            {text.split('\n').map((line, index) => {
              const parsed = { level: 2, content: line }
              return (
                <div
                  key={index}
                  ref={(element) => { markdownLineRefs.current[index] = element }}
                  className={`inline-text markdown-level-${parsed.level}`}
                  contentEditable={!busy}
                  suppressContentEditableWarning
                  role="textbox"
                  aria-label={block.type === 'paragraph' ? `Paragraph line ${index + 1}` : 'Heading content'}
                  aria-multiline="false"
                  data-placeholder={index === 0 ? 'Start writing...' : ''}
                  onInput={(event) => handleMarkdownInput(index, event.currentTarget)}
                  onKeyDown={(event) => handleMarkdownKeyDown(event, index)}
                  onBlur={(event) => {
                    if (!event.currentTarget.parentElement?.contains(event.relatedTarget)) persist({ ...block.content, text: textRef.current })
                  }}
                >
                  {parsed.content}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </li>
  )
}
