# PythonTrainer

PythonTrainer es una aplicación local y offline para practicar Python con lecciones, ejercicios y validación automática.  
Está pensado para aprendizaje progresivo, guardando avance en JSON y permitiendo trabajar tanto en interfaz gráfica como en consola.

## Cómo ejecutar

Desde la carpeta `python_trainer`:

- **GUI (Tkinter):** `python main.py`
- **CLI:** `python main.py --cli`
- **Modo examen (GUI):** `python main.py --exam`
- **Modo examen (CLI):** `python main.py --cli --exam`
- **Modo VSCode-like (pywebview + Monaco):** `python -m ui.vscode_app`

## Cómo ejecutar tests

Desde la raíz del proyecto:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Arquitectura

Flujo principal:

1. `main.py` inicia la aplicación y decide el modo de ejecución según flags.
2. La capa `ui/` (CLI, Tkinter o VSCode-like) gestiona interacción del usuario.
3. La capa `core/` ejecuta lógica de negocio: catálogo, runner, validador y progreso.
4. El progreso se persiste en `%LOCALAPPDATA%\PythonTrainer\progress.json`.
5. Los contenidos base viven en `data/catalog.json` (con fallback interno si falla).

Esquema simplificado:

```text
main.py
  ↓
ui/ (cli.py | gui.py | vscode_app.py)
  ↓
core/ (exercises, runner, validator, progress)
  ↓
data/ + almacenamiento local del usuario
```

## Decisiones técnicas

- **Offline-first:** sin servicios cloud; toda la ejecución y persistencia es local.
- **Compatibilidad didáctica:** CLI y GUI usan la misma lógica de `core/` para evitar comportamientos divergentes.
- **Seguridad pragmática:** el runner bloquea imports peligrosos y ejecuta en subproceso con timeout.
- **Fallbacks robustos:** si `ruff`, `pyright` o `pyright-langserver` no están disponibles, la UI sigue funcionando con avisos claros.
- **Persistencia estable:** escritura de progreso en JSON con enfoque conservador para evitar corrupción.

## Estructura del proyecto

- `main.py`: punto de entrada principal.
- `core/`: lógica de dominio (ejecución, validación, progreso, catálogo).
- `ui/`: interfaces de usuario (CLI, Tkinter y VSCode-like).
- `data/`: datos estáticos, incluyendo catálogo de ejercicios.
- `tests/`: tests unitarios.

## Formato de catálogo (JSON)

Ruta: `python_trainer/data/catalog.json`.  
Si existe y es válido, se usa; si no, la app aplica fallback al catálogo interno.

Ejemplo mínimo:

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
              "checks": [
                { "type": "equals", "var": "saludo", "expected": "Hola" }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

## Modo VSCode-like (MVP)

Recomendado en Windows con Python 3.12:

```bash
python -m pip install -r requirements-dev.txt
python -m pip install ruff pyright pywebview
python -m ui.vscode_app
```

Si usas Python 3.14 para el curso, crea un entorno virtual separado con Python 3.12 para este modo.
