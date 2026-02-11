# PythonTrainer

PythonTrainer es una aplicación local y offline para practicar Python mediante lecciones y ejercicios guiados.

Está pensada para aprender a tu ritmo, validar resultados y guardar el progreso sin depender de internet ni de librerías externas.

La aplicación funciona tanto en modo gráfico (Tkinter) como en modo consola, e incluye un modo examen que oculta pistas y soluciones.

## Cómo ejecutar

Desde la carpeta `python_trainer`:

- **GUI:**  
  `python main.py`

- **CLI:**  
  `python main.py --cli`

- **Modo examen (GUI):**  
  `python main.py --exam`

- **Modo examen (CLI):**  
  `python main.py --cli --exam`

## Cómo ejecutar tests

Desde la raíz del proyecto (donde se encuentra `requirements-dev.txt`):

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Arquitectura de la aplicación

Flujo principal, en pasos simples:

1. `main.py` arranca la app.
2. Decide si usar GUI o CLI según los flags.
3. La interfaz (GUI/CLI) llama a funciones de `core/`.
4. `core/` gestiona la lógica y el progreso.
5. El progreso se guarda en disco.

Esquema:

```
main.py
  ↓
ui (cli / gui)
  ↓
core (lógica)
  ↓
data (progress.json)
```

## Formato de catalogo (JSON)

El archivo se coloca en `python_trainer/data/catalog.json`. Si existe y es valido, se usa; si no, la app usa el catalogo interno.

Formato minimo:

```json
{
  "version": 1,
  "modules": [
    {
      "id": "basics-01",
      "title": "Basicos",
      "lessons": [
        {
          "id": "b1_l1",
          "title": "Primeros pasos",
          "exercises": [
            {
              "id": "b1_l1_e1",
              "title": "Hola",
              "statement": "Crea la variable saludo y muestrala.",
              "starter_code": "saludo = ''",
              "checks": [ { "type": "equals", "var": "saludo", "expected": "Hola" } ]
            }
          ]
        }
      ]
    }
  ]
}
```

## Modo VSCode-like (MVP)

Instala dependencias del modo editor web:

```bash
python -m pip install -r requirements-dev.txt
```

Lanza el modo VSCode-like (pywebview + Monaco):

```bash
python -m ui.vscode_app
```

Incluye:

- Monaco Editor en tema oscuro
- Botones Run y Run Exam
- Panel Output (stdout/stderr)
- Panel Problems con markers de Monaco
- Diagnosticos de sintaxis siempre (aunque falten herramientas externas)
- Lint con `ruff` y typecheck con `pyright` (si estan instalados)
- Autocompletado y hover usando `pyright-langserver` local

### Requisitos y ejecucion recomendada (Windows)

- Requisito recomendado para VSCode UI: Python 3.12.
- Instalacion:
  - `python -m pip install -r requirements-dev.txt`
  - `python -m pip install ruff pyright pywebview`
- Ejecucion:
  - `python -m ui.vscode_app`
- Nota:
  - Si usas Python 3.14 para el curso, crea un venv con 3.12 para este modo.
  - El backend intenta ejecutar `ruff` con `python -m ruff` para no depender de PATH.
