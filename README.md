# EDF Repago Streamlit

App Streamlit limpia para publicar el dashboard EDF.

## Archivos que debe tener el repo

- `streamlit_app.py`
- `edf_importer.py`
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

La app tiene un boton **Sincronizar Drive e importar** en la barra lateral.

Lee esta carpeta:

```text
https://drive.google.com/drive/folders/1cukgXLUaPsEDK_yD7tSwgaBFZAbiDUot
```

Archivos esperados:

- Semaforo actualizado `.xlsx`
- `edf 1.xlsx`
- `edf 2.xlsx`
- `PI 2026...xlsb`
- Plantilla clientes `.xlsx`
- todos los `venta*.txt`

Como alternativa, para generar `db.json`, usar la app local Node y el boton Importar. Luego copiar:

```text
C:\Users\triesgo\Documents\Codex\2026-05-21\este-es-el-archivo-mas-importante\data\db.json
```

a:

```text
data\db.json
```

No subir `db.json` a un repo publico si contiene datos privados.
