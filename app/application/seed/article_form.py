"""Formulario inicial del producto "Artículo científico".

Es solo el punto de partida: una vez cargado, los administradores lo modifican desde el sistema
(nuevos borradores y versiones) sin tocar código ni base de datos.
"""

from app.domain.forms.definition import SectionInput

ARTICLE_CODE = "ARTICULO"
ARTICLE_NAME = "Artículo científico"
ARTICLE_DESCRIPTION = "Artículo publicado en una revista científica."
ARTICLE_FOLDER = "Articulos"  # carpeta de los soportes: <cédula>/Articulos/Solicitud N

ARTICLE_SECTIONS: list[SectionInput] = [
    {
        "title": "Datos del artículo",
        "fields": [
            {
                "key": "cedula",
                "label": "Cédula",
                "type": "CEDULA",
                "required_to_submit": True,
                "help_text": "Define la carpeta donde se guardan los soportes",
            },
            {
                "key": "titulo",
                "label": "Título del artículo",
                "type": "TEXT",
                "required_to_submit": True,
                "max_length": 500,
            },
            {
                "key": "anio_publicacion",
                "label": "Año de publicación",
                "type": "INTEGER",
                "required_to_submit": True,
                "min_value": 1900,
                "max_value": 2100,
            },
            {"key": "fecha_publicacion", "label": "Fecha de publicación", "type": "DATE"},
            {"key": "doi", "label": "DOI", "type": "DOI"},
            {"key": "url", "label": "URL del artículo", "type": "URL"},
        ],
    },
    {
        "title": "Datos de la revista",
        "fields": [
            {
                "key": "revista",
                "label": "Nombre de la revista",
                "type": "TEXT",
                "required_to_submit": True,
                "max_length": 300,
            },
            {"key": "issn", "label": "ISSN", "type": "ISSN"},
            {"key": "eissn", "label": "eISSN", "type": "ISSN"},
            {"key": "volumen", "label": "Volumen", "type": "TEXT", "max_length": 20},
            {"key": "numero", "label": "Número", "type": "TEXT", "max_length": 20},
            {"key": "paginas", "label": "Páginas", "type": "TEXT", "max_length": 30},
        ],
    },
    {
        "title": "Soportes",
        "description": "Documentos que respaldan el artículo.",
        "fields": [
            {
                "key": "soporte_articulo",
                "label": "Artículo publicado",
                "type": "SUPPORT",
                "required_to_submit": True,
                "help_text": "PDF del artículo tal como fue publicado",
                "allowed_types": ["pdf"],
            },
            {
                "key": "soporte_aceptacion",
                "label": "Carta de aceptación",
                "type": "SUPPORT",
                "help_text": "Opcional. PDF o documento de Word",
                "allowed_types": ["pdf", "doc", "docx"],
            },
        ],
    },
]
