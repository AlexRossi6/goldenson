type InlineNoticeProps = {
  tone: 'error' | 'info'
  message: string
}

export function InlineNotice({ tone, message }: InlineNoticeProps) {
  return (
    <p className={`inline-notice ${tone === 'error' ? 'is-error' : 'is-info'}`} role={tone === 'error' ? 'alert' : 'status'}>
      {message}
    </p>
  )
}
