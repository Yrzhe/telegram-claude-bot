import { useFilesStore } from '../../stores/files'

export function Toast() {
  const toastMessage = useFilesStore((state) => state.toastMessage)
  const toastVisible = useFilesStore((state) => state.toastVisible)

  if (!toastMessage) return null

  return (
    <div className={`toast ${!toastVisible ? 'hiding' : ''}`}>
      {toastMessage}
    </div>
  )
}
