import { Badge, Tooltip, TooltipContent, TooltipTrigger } from '@juanarenas31/metrik-ui'

interface Props {
  count: number
  /** Qué se cuenta; sale en el tooltip y en aria-label. */
  label: string
  /** Detalle para el tooltip (p. ej. los nombres). */
  names?: string[]
  /** Aviso cuando es 0 (un cero suele ser un problema: sin productos, sin revisores). */
  emptyHint?: string
}

/** Una cantidad en vez de texto: "3", "9+"; el detalle aparece al pasar el cursor. */
export function CountBadge({ count, label, names = [], emptyHint }: Props) {
  const shown = count > 9 ? '9+' : String(count)
  const tip = count === 0 ? (emptyHint ?? `Sin ${label}`) : `${count} ${label}${names.length ? `: ${names.join(', ')}` : ''}`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex" role="img" aria-label={tip}>
          <Badge tone={count === 0 ? 'warning' : 'primary'} className="min-w-7 justify-center tabular-nums">{shown}</Badge>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{tip}</TooltipContent>
    </Tooltip>
  )
}
