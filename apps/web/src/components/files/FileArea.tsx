import { useRef, useState, type ChangeEvent } from 'react'

import type { FileMetadata } from '../../types/api'
import { getFileDownloadUrl } from '../../api/files'

type FileAreaProps = {
  files: FileMetadata[]
  title?: string
  loading: boolean
  errorMessage: string | null
  uploading: boolean
  onUpload?: (file: File) => Promise<void>
  onDelete: (file: FileMetadata) => void
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

export function FileArea({ files, title = 'Files', loading, errorMessage, uploading, onUpload, onDelete }: FileAreaProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [localError, setLocalError] = useState<string | null>(null)

  const chooseFile = () => inputRef.current?.click()
  const handleChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setLocalError(null)
    try {
      if (onUpload) await onUpload(file)
    } catch {
      setLocalError('This file could not be added.')
    }
  }

  return (
    <section className="file-area" aria-labelledby={`${title.toLowerCase().replaceAll(' ', '-')}-title`}>
      <div className="file-area-header">
        <div>
          <p className="panel-label" id={`${title.toLowerCase().replaceAll(' ', '-')}-title`}>{title}</p>
          <span className="file-count">{files.length} {files.length === 1 ? 'file' : 'files'}</span>
        </div>
        {onUpload && <>
          <button type="button" className="tree-icon" onClick={chooseFile} aria-label="Add file">+</button>
          <input ref={inputRef} className="visually-hidden" type="file" onChange={handleChange} />
        </>}
      </div>
      {(errorMessage || localError) && <p className="file-error" role="alert">{errorMessage ?? localError}</p>}
      {loading || uploading ? <p className="file-empty">{uploading ? 'Uploading...' : 'Loading files...'}</p> : files.length === 0 ? <p className="file-empty">No files yet.</p> : (
        <ul className="file-list">
          {files.map((file) => (
            <li key={file.id} className="file-item">
              <a href={getFileDownloadUrl(file.id)} className="file-link">{file.name}</a>
              <span>{formatSize(file.size)}</span>
              <button type="button" className="text-button danger-link" onClick={() => onDelete(file)} aria-label={`Delete ${file.name}`}>Delete</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
