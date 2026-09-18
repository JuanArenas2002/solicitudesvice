import type { ComponentType } from 'react'
import { Link } from 'react-router-dom'
import type { LucideProps } from 'lucide-react'
import { Button, Tooltip, TooltipContent, TooltipTrigger, type ButtonProps } from '@juanarenas31/metrik-ui'

interface Props extends Omit<ButtonProps, 'children' | 'size' | 'aria-label'> {
  icon: ComponentType<LucideProps>
  /** Nombre de la acción: va en el tooltip y como aria-label (el botón no muestra texto). */
  label: string
  /** Si se indica, el botón es un enlace a esa ruta. */
  to?: string
}

/** Acción sin texto: solo el icono; el nombre aparece al pasar el cursor. */
export function IconButton({ icon: Icon, label, to, variant = 'outline', ...props }: Props) {
  const content = <Icon className="size-4" aria-hidden />
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {to ? (
          <Button asChild size="sm" variant={variant} aria-label={label}><Link to={to}>{content}</Link></Button>
        ) : (
          <Button size="sm" variant={variant} aria-label={label} {...props}>{content}</Button>
        )}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}
