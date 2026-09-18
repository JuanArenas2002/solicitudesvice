import type { ComponentType } from 'react'
import {
  Archive, CircleCheck, CircleX, Globe, MessageSquareWarning, Pencil, RefreshCw, ScanSearch, Send,
  type LucideProps,
} from 'lucide-react'
import { Badge, Tooltip, TooltipContent, TooltipTrigger, cn } from '@juanarenas31/metrik-ui'
import type { FormStatus, RequestStatus } from '../api/types'
import { FORM_STATUS, STATUS } from '../constants'

type Icon = ComponentType<LucideProps>

/** Los estados se muestran con iconos; el nombre queda en el tooltip y en aria-label (accesibilidad). */
export const STATUS_ICON: Record<RequestStatus, Icon> = {
  BORRADOR: Pencil,
  ENVIADA: Send,
  EN_REVISION: ScanSearch,
  CORRECCION_SOLICITADA: MessageSquareWarning,
  REENVIADA: RefreshCw,
  APROBADA: CircleCheck,
  RECHAZADA: CircleX,
}

const FORM_STATUS_ICON: Record<FormStatus, Icon> = {
  BORRADOR: Pencil,
  PUBLICADA: Globe,
  RETIRADA: Archive,
}

function IconBadge({ Icon, label, tone, className }: {
  Icon: Icon; label: string; tone: React.ComponentProps<typeof Badge>['tone']; className?: string
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex" role="img" aria-label={label}>
          <Badge tone={tone} className={cn('px-1.5', className)}><Icon className="size-4" aria-hidden /></Badge>
        </span>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

export function StatusBadge({ status, className }: { status: RequestStatus; className?: string }) {
  return <IconBadge Icon={STATUS_ICON[status]} label={STATUS[status].label} tone={STATUS[status].tone} className={className} />
}

export function FormStatusBadge({ status }: { status: FormStatus }) {
  return <IconBadge Icon={FORM_STATUS_ICON[status]} label={FORM_STATUS[status].label} tone={FORM_STATUS[status].tone} />
}
