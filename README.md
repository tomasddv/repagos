# EDF Repago Streamlit

App Streamlit limpia para publicar el dashboard EDF.

## Archivos que debe tener el repo

- `streamlit_app.py`
- `requirements.txt`
- `runtime.txt`
- `.gitignore`
- `.streamlit/config.toml`

Opcional:

- `data/db.json`

Si no se sube `data/db.json`, la app permite cargarlo manualmente desde la barra lateral.

## Deploy en Streamlit

- Repository: el repo nuevo que crees
- Branch: `main`
- Main file path: `streamlit_app.py`

## Datos

Para generar `db.json`, usar la app local Node y el boton Importar. Luego copiar:

```text
C:\Users\triesgo\Documents\Codex\2026-05-21\este-es-el-archivo-mas-importante\data\db.json
```

a:

```text
data\db.json
```

No subir `db.json` a un repo publico si contiene datos privados.
