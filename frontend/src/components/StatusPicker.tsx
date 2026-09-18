import { ToggleGroup, ToggleGroupItem, Tooltip, TooltipContent, TooltipTrigger } from '@juanarenas31/metrik-ui'
import type { RequestStatus } from '../api/types'
import { STATUS } from '../constants'
import { STATUS_ICON } from './StatusBadge'

interface Props {
  value: RequestStatus | ''
  onChange: (status: RequestStatus | '') => void
  /** Estados que se ofrecen (por defecto todos). */
  options?: RequestStatus[]
  label: string
}

/** Elige un estado con iconos (el nombre sale en el tooltip). Volver a pulsar el elegido lo quita. */
export function StatusPicker({ value, onChange, options = Object.keys(STATUS) as RequestStatus[], label }: Props) {
  return (
    <ToggleGroup type="single" value={value} aria-label={label} className="flex-wrap justify-start"
      onValueChange={(v) => onChange((v as RequestStatus | '') ?? '')}>
      {options.map((s) => {
        const Icon = STATUS_ICON[s]
        return (
          <Tooltip key={s}>
            <TooltipTrigger asChild>
              <ToggleGroupItem value={s} aria-label={STATUS[s].label}><Icon className="size-4" aria-hidden /></ToggleGroupItem>
            </TooltipTrigger>
            <TooltipContent>{STATUS[s].label}</TooltipContent>
          </Tooltip>
        )
      })}
    </ToggleGroup>
  )
}
