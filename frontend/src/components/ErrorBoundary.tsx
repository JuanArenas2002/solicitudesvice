import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Alert, AlertDescription, AlertTitle, Button } from '@juanarenas31/metrik-ui'

interface Props {
  children: ReactNode
  /** Qué mostrar si algo falla; por defecto un aviso con el detalle y opciones para reintentar. */
  fallback?: (error: Error, reset: () => void) => ReactNode
  onError?: (error: Error) => void
}

/** Una falla al dibujar una pantalla o un diálogo muestra un aviso con el error en vez de dejar todo en blanco. */
export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) { return { error } }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Error de interfaz:', error, info.componentStack)
    this.props.onError?.(error)
  }

  reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    if (this.props.fallback) return this.props.fallback(error, this.reset)
    return (
      <Alert tone="danger" className="my-4">
        <AlertTitle>Algo falló al mostrar esta pantalla</AlertTitle>
        <AlertDescription className="space-y-3">
          <p className="break-words font-mono text-xs">{error.message}</p>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={this.reset}>Reintentar</Button>
            <Button size="sm" variant="ghost" onClick={() => window.location.reload()}>Recargar la página</Button>
          </div>
        </AlertDescription>
      </Alert>
    )
  }
}
