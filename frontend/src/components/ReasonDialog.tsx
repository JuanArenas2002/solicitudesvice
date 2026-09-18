import { useState } from 'react'
import {
  Alert, AlertDescription, Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader,
  DialogTitle, FloatingTextarea,
} from '@juanarenas31/metrik-ui'

interface Props {
  title: string
  label: string
  required: boolean
  pending: boolean
  error?: string
  onConfirm: (text: string) => void
  onCancel: () => void
}

/** Diálogo con un texto (motivo del rechazo, detalle de la corrección...). Se monta solo mientras está abierto. */
export function ReasonDialog({ title, label, required, pending, error, onConfirm, onCancel }: Props) {
  const [text, setText] = useState('')
  return (
    <Dialog open onOpenChange={(o) => !o && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{required ? 'Este dato es obligatorio.' : 'Este dato es opcional.'}</DialogDescription>
        </DialogHeader>
        <FloatingTextarea label={label} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} rows={4} />
        {error && <Alert tone="danger"><AlertDescription>{error}</AlertDescription></Alert>}
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>Cancelar</Button>
          <Button loading={pending} disabled={required && !text.trim()} onClick={() => onConfirm(text.trim())}>Confirmar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
