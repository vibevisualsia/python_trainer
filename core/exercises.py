import logging
import sys
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from core.catalog import load_catalog

logger = logging.getLogger("PythonTrainer.exercises")
_CACHED_CATALOG = None

# Definicion de modulos, lecciones y ejercicios (progresion obligatoria)
MODULES: List[Dict] = [
    {
        "id": "module1",
        "title": "Fundamentos",
        "description": "Primeros pasos con print, variables, tipos, listas e if.",
        "lessons": [
            {
                "id": "m1_l1",
                "title": "Print y variables",
                "key_points": [
                    "print muestra texto en pantalla.",
                    "Asigna primero, imprime despues.",
                    "Usa nombres descriptivos para variables.",
                ],
                "explanation": [
                    "print muestra informacion en pantalla.",
                    "Puedes guardar texto en variables para reutilizarlo.",
                    "Las comillas simples o dobles crean cadenas de texto.",
                    "Asignar es usar = (no es igualdad matematica).",
                    "Primero asigna, luego imprime.",
                    "Un buen habito es nombrar la variable segun su uso.",
                ],
                "exercises": [
                    {
                        "id": "m1_l1_e1",
                        "title": "Imprime un saludo",
                        "statement": "Crea la variable saludo con el texto 'Hola, Python!' e imprimelo.",
                        "example": "mensaje = 'Hola, clase'\nprint(mensaje)",
                        "starter_code": "saludo = ''\n# imprime aqui el saludo\n",
                        "accepted_vars": ["saludo", "mensaje"],
                        "hints": [
                            "Asigna el texto exacto a la variable saludo.",
                            "Llama a print(saludo) para mostrarlo.",
                        ],
                        "solution": "saludo = 'Hola, Python!'\nprint(saludo)\n",
                        "checks": [
                            {
                                "type": "equals",
                                "var": "saludo",
                                "expected": "Hola, Python!",
                                "message": "La variable saludo debe contener 'Hola, Python!'.",
                            },
                            {
                                "type": "output_contains",
                                "expected": "Hola, Python!",
                                "message": "Debes imprimir el saludo en pantalla.",
                            },
                        ],
                    },
                    {
                        "id": "m1_l1_e2",
                        "title": "Suma simple",
                        "statement": "Usa las variables a=2 y b=3 para calcular la suma en total e imprimelo.",
                        "example": "x = 4\ny = 1\nresultado = x + y\nprint(resultado)",
                        "starter_code": "a = 2\nb = 3\n# calcula total y muestralo\n",
                        "accepted_vars": ["total", "resultado"],
                        "hints": [
                            "La suma se hace con el operador +.",
                            "Guarda el resultado en total y luego usa print(total).",
                        ],
                        "solution": "a = 2\nb = 3\ntotal = a + b\nprint(total)\n",
                        "checks": [
                            {
                                "type": "equals",
                                "var": "total",
                                "expected": 5,
                                "message": "total debe valer 5.",
                            },
                            {
                                "type": "output_contains",
                                "expected": "5",
                                "message": "Imprime el resultado de la suma.",
                            },
                        ],
                    },
                ],
            },
            {
                "id": "m1_l2",
                "title": "Tipos basicos",
                "key_points": [
                    "int y float son numericos; str es texto; bool es True/False.",
                    "int() y float() convierten texto numerico.",
                    "F-strings para combinar texto y valores.",
                ],
                "explanation": [
                    "Los tipos comunes: int, float, str y bool.",
                    "Para convertir texto a numero usa int() o float().",
                    "Puedes ver el tipo con type(variable) al depurar.",
                    "Las f-strings ayudan a combinar texto y valores.",
                    "Recuerda que input devuelve texto; aqui no usamos input.",
                    "Mantener nombres claros facilita leer el codigo.",
                ],
                "exercises": [
                    {
                        "id": "m1_l2_e1",
                        "title": "Convertir texto a numero",
                        "statement": "Convierte el texto '42' a entero en la variable numero.",
                        "example": "dato = '10'\nvalor = int(dato)\nprint(valor)",
                        "starter_code": "texto = '42'\nnumero = None\n# convierte texto a entero en numero\n",
                        "accepted_vars": ["numero", "valor"],
                        "hints": [
                            "Usa la funcion int() con el texto.",
                            "numero debe ser un int con valor 42.",
                        ],
                        "solution": "texto = '42'\nnumero = int(texto)\n",
                        "checks": [
                            {
                                "type": "equals",
                                "var": "numero",
                                "expected": 42,
                                "message": "numero debe ser 42 (int).",
                            }
                        ],
                    },
                    {
                        "id": "m1_l2_e2",
                        "title": "Armar un mensaje",
                        "statement": "Usa nombre y edad para crear mensaje con f-string: 'Hola Ana, tienes 21'.",
                        "example": "persona = 'Luis'\nanos = 30\ntexto = f\"Hola {persona}, tienes {anos}\"\nprint(texto)",
                        "starter_code": "nombre = 'Ana'\nedad = 21\nmensaje = ''\n# completa el mensaje\n",
                        "accepted_vars": ["mensaje", "texto"],
                        "hints": [
                            "Usa f-string: f\"Hola {nombre}, tienes {edad}\"",
                            "Guarda en mensaje y luego imprime mensaje.",
                        ],
                        "solution": "nombre = 'Ana'\nedad = 21\nmensaje = f\"Hola {nombre}, tienes {edad}\"\nprint(mensaje)\n",
                        "checks": [
                            {
                                "type": "equals",
                                "var": "mensaje",
                                "expected": "Hola Ana, tienes 21",
                                "message": "mensaje debe ser 'Hola Ana, tienes 21'.",
                            },
                            {
                                "type": "output_contains",
                                "expected": "Hola Ana, tienes 21",
                                "message": "Debes imprimir el mensaje.",
                            },
                        ],
                    },
                ],
            },
            {
                "id": "m1_l3",
                "title": "Listas basicas",
                "key_points": [
                    "Crea listas con corchetes [].",
                    "append agrega un elemento al final.",
                    "len(lista) da el tamano.",
                ],
                "explanation": [
                    "Una lista guarda varios valores en orden.",
                    "Se crean con corchetes: [1, 2, 3].",
                    "append agrega un elemento al final.",
                    "Puedes acceder por indice: lista[0].",
                    "len(lista) devuelve cuantos elementos hay.",
                    "Las listas pueden contener texto, numeros u otros tipos.",
                ],
                "exercises": [
                    {
                        "id": "m1_l3_e1",
                        "title": "Crear y agregar a una lista",
                        "statement": "Crea la lista frutas con 'manzana' y 'pera', agrega 'uva' y guardala en frutas.",
                        "example": "colores = ['rojo', 'azul']\ncolores.append('verde')\nprint(colores)",
                        "starter_code": "frutas = ['manzana', 'pera']\n# agrega aqui la nueva fruta\n",
                        "accepted_vars": ["frutas", "lista"],
                        "hints": [
                            "Usa frutas.append('uva').",
                            "Revisa que la lista final tenga tres elementos.",
                        ],
                        "solution": "frutas = ['manzana', 'pera']\nfrutas.append('uva')\nprint(frutas)\n",
                        "checks": [
                            {
                                "type": "equals",
                                "var": "frutas",
                                "expected": ["manzana", "pera", "uva"],
                                "message": "La lista debe ser ['manzana', 'pera', 'uva'].",
                            },
                        ],
                    },
                ],
            },
            {
                "id": "m1_l4",
                "title": "if basico",
                "key_points": [
                    "if ejecuta solo si la condicion es True.",
                    "Comparar con ==, asignar con =.",
                    "Paridad: num % 2 == 0.",
                ],
                "explanation": [
                    "if permite decidir segun una condicion booleana.",
                    "Expresiones de comparacion devuelven True o False.",
                    "Recuerda usar == para comparar, = para asignar.",
                    "Puedes combinar condiciones con and y or.",
                    "Para paridad, usa numero % 2 == 0.",
                    "Siempre alinea bien el bloque indentado.",
                ],
                "exercises": [
                    {
                        "id": "m1_l4_e1",
                        "title": "Par o impar",
                        "statement": "Con numero = 7, crea es_par con True si es par, False si no. Imprime es_par.",
                        "example": "n = 10\nresultado = n % 2 == 0\nprint(resultado)",
                        "starter_code": "numero = 7\nes_par = None\n# asigna True o False a es_par\n",
                        "accepted_vars": ["es_par", "resultado"],
                        "hints": [
                            "Un numero es par si numero % 2 == 0.",
                            "Guarda el resultado booleano en es_par y usa print.",
                        ],
                        "solution": "numero = 7\nes_par = numero % 2 == 0\nprint(es_par)\n",
                        "checks": [
                            {
                                "type": "equals",
                                "var": "es_par",
                                "expected": False,
                                "message": "Para 7, es_par debe ser False.",
                            },
                        ],
                    },
                ],
            },
        ],
    },
    {
        "id": "module2",
        "title": "Transformaciones con map",
        "description": "Uso de lambda y map para listas.",
        "lessons": [
            {
                "id": "m2_l1",
                "title": "lambda + map",
                "key_points": [
                    "lambda define funciones cortas en linea.",
                    "map aplica una funcion a cada elemento de un iterable.",
                    "Formula C -> F: F = C * 9 / 5 + 32.",
                ],
                "explanation": [
                    "lambda define funciones cortas en linea.",
                    "map aplica una funcion a cada elemento de un iterable.",
                    "El resultado de map es un iterable; usa list(...) para materializarlo.",
                    "Puedes combinar lambda con operaciones matematicas sencillas.",
                    "Formula Celsius -> Fahrenheit: F = C * 9 / 5 + 32.",
                    "Inversa Fahrenheit -> Celsius: C = (F - 32) * 5 / 9.",
                    "Es util cuando quieres transformar listas sin escribir for.",
                    "Recuerda que map no modifica la lista original.",
                ],
                "exercises": [
                    {
                        "id": "m2_l1_e1",
                        "title": "Celsius a Fahrenheit",
                        "statement": "Convierte la lista celsius a Fahrenheit usando map y lambda en la variable result.",
                        "example": "valores = [1, 5]\nconvertidos = list(map(lambda x: x * 2, valores))\nprint(convertidos)",
                        "starter_code": "celsius = [0, 12, 19, 21]\nresult = []\n# usa map + lambda para llenar result\n",
                        "accepted_vars": ["result", "resultado", "out"],
                        "hints": [
                            "Formula: F = C * 9 / 5 + 32",
                            "Usa result = list(map(lambda c: ..., celsius))",
                        ],
                        "solution": "celsius = [0, 12, 19, 21]\nresult = list(map(lambda c: c * 9 / 5 + 32, celsius))\nprint(result)\n",
                        "checks": [
                            {
                                "type": "list_close",
                                "var": "result",
                                "expected": [32.0, 53.6, 66.2, 69.8],
                                "message": "result debe contener los Fahrenheit correctos.",
                            }
                        ],
                    }
                ],
            }
        ],
    },
]


def _catalog_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent
    return base_path / "data" / "catalog.json"


def _get_catalog_modules() -> Optional[List[Dict]]:
    global _CACHED_CATALOG
    if _CACHED_CATALOG is None:
        _CACHED_CATALOG = load_catalog(_catalog_path())
    if not _CACHED_CATALOG:
        return None
    return _CACHED_CATALOG.get("modules")


def get_modules() -> List[Dict]:
    modules = _get_catalog_modules()
    if modules:
        return modules
    return MODULES


def reload_catalog() -> bool:
    global _CACHED_CATALOG
    _CACHED_CATALOG = None
    _CACHED_CATALOG = load_catalog(_catalog_path())
    if _CACHED_CATALOG:
        logger.info("Catalogo recargado OK")
        return True
    logger.warning("No se pudo cargar catalogo, usando contenido por defecto")
    return False


def get_module_by_id(module_id: str) -> Dict:
    for module in get_modules():
        if module["id"] == module_id:
            return module
    raise ValueError(f"Modulo no encontrado: {module_id}")


def list_all_exercises() -> List[Dict]:
    items: List[Dict] = []
    for module in get_modules():
        for lesson in module["lessons"]:
            for exercise in lesson["exercises"]:
                enriched = dict(exercise)
                enriched["module_id"] = module["id"]
                enriched["lesson_id"] = lesson["id"]
                items.append(enriched)
    return items


def find_exercise(module_id: str, lesson_id: str, exercise_id: str) -> Dict:
    module = get_module_by_id(module_id)
    for lesson in module["lessons"]:
        if lesson["id"] != lesson_id:
            continue
        for exercise in lesson["exercises"]:
            if exercise["id"] == exercise_id:
                enriched = dict(exercise)
                enriched["module_id"] = module_id
                enriched["lesson_id"] = lesson_id
                return enriched
    raise ValueError(f"Ejercicio no encontrado: {module_id}/{lesson_id}/{exercise_id}")


def first_exercise_of_module(module_id: str) -> Dict:
    module = get_module_by_id(module_id)
    lesson = module["lessons"][0]
    exercise = lesson["exercises"][0]
    enriched = dict(exercise)
    enriched["module_id"] = module_id
    enriched["lesson_id"] = lesson["id"]
    return enriched


def find_indices(modules: List[Dict], module_id: str, lesson_id: str, exercise_id: str) -> Tuple[int, int, int]:
    for mi, module in enumerate(modules):
        if module["id"] != module_id:
            continue
        for li, lesson in enumerate(module["lessons"]):
            if lesson["id"] != lesson_id:
                continue
            for ei, exercise in enumerate(lesson["exercises"]):
                if exercise["id"] == exercise_id:
                    return mi, li, ei
    raise ValueError("No se encontraron indices para la posicion indicada.")


def next_position(modules: List[Dict], module_id: str, lesson_id: str, exercise_id: str) -> Optional[Tuple[str, str, str]]:
    mi, li, ei = find_indices(modules, module_id, lesson_id, exercise_id)
    module = modules[mi]
    lesson = module["lessons"][li]
    if ei + 1 < len(lesson["exercises"]):
        nex = lesson["exercises"][ei + 1]
        return module["id"], lesson["id"], nex["id"]
    if li + 1 < len(module["lessons"]):
        next_lesson = module["lessons"][li + 1]
        nex = next_lesson["exercises"][0]
        return module["id"], next_lesson["id"], nex["id"]
    if mi + 1 < len(modules):
        next_module = modules[mi + 1]
        first_lesson = next_module["lessons"][0]
        first_ex = first_lesson["exercises"][0]
        return next_module["id"], first_lesson["id"], first_ex["id"]
    return None
