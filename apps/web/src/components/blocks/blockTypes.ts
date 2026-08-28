export type BlockTypeDefinition = {
  type: string
  name: string
  description: string
  keywords?: string[]
}

export const BLOCK_TYPES: BlockTypeDefinition[] = [
  { type: 'paragraph', name: 'Paragraph', description: 'A place for notes and ideas.', keywords: ['text', 'writing', 'note'] },
  { type: 'todo', name: 'To-do', description: 'A simple list of tasks.', keywords: ['task', 'checklist'] },
  { type: 'code', name: 'Code', description: 'A block for code snippets.', keywords: ['snippet', 'programming'] },
]