import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Alert, AlertDescription, Button, Card, CardContent, EmptyState, Table, TableBody, TableCell, TableHead,
  TableHeader, TableRow,
} from '@juanarenas31/metrik-ui'
import { catalogApi } from '../api'
import { PageHeader } from '../components/PageHeader'
import { QueryState } from '../components/QueryState'
import { FormStatusBadge } from '../components/StatusBadge'
import { formatDateTime } from '../constants'
import { useAsync } from '../hooks/useAsync'
import { useSubmit } from '../hooks/useSubmit'

export default function ProductFormsPage() {
  const productId = Number(useParams().productId)
  const navigate = useNavigate()
  const products = useAsync(catalogApi.productTypes, [])
  const versions = useAsync(() => catalogApi.versions(productId), [productId])
  const open = useSubmit(() => catalogApi.openDraft(productId))

  const product = products.data?.items.find((p) => p.id === productId)
  const onNewDraft = async () => {
    const draft = await open.run()
    if (draft) navigate(`/productos/${productId}/versiones/${draft.id}`)
  }

  return (
    <>
      <PageHeader
        title={product ? `Formularios de ${product.name}` : 'Formularios'}
        description="Las solicitudes conservan la versión con la que empezaron; publicar una nueva solo afecta a las solicitudes nuevas."
        actions={<Button asChild variant="ghost"><Link to="/productos">Volver</Link></Button>}
      />
      {open.error && <Alert tone="danger" className="mb-4"><AlertDescription>{open.error.message}</AlertDescription></Alert>}
      <QueryState query={versions}>
        {(list) => (
          <Card>
            <CardContent className="space-y-4 pt-6">
              {!list.some((v) => v.status === 'BORRADOR') && (
                <Button loading={open.pending} onClick={onNewDraft}>Nueva versión (borrador)</Button>
              )}
              {list.length === 0 ? (
                <EmptyState title="Sin versiones" description="Este producto aún no tiene formulario." />
              ) : (
                <Table stackable>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Versión</TableHead><TableHead>Estado</TableHead><TableHead>Creada</TableHead>
                      <TableHead>Publicada</TableHead><TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {list.map((v) => (
                      <TableRow key={v.id}>
                        <TableCell label="Versión" className="font-medium">v{v.version_number}</TableCell>
                        <TableCell label="Estado"><FormStatusBadge status={v.status} /></TableCell>
                        <TableCell label="Creada">{formatDateTime(v.created_at)}</TableCell>
                        <TableCell label="Publicada">{v.published_at ? formatDateTime(v.published_at) : '—'}</TableCell>
                        <TableCell className="text-right">
                          <Button asChild size="sm" variant="outline">
                            <Link to={`/productos/${productId}/versiones/${v.id}`}>{v.status === 'BORRADOR' ? 'Editar' : 'Ver'}</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        )}
      </QueryState>
    </>
  )
}
