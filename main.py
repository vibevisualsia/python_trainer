import argparse
import logging

from core.logging_setup import setup_logging


def main() -> None:
    setup_logging()
    logger = logging.getLogger("PythonTrainer")
    logger.info("Arranque de la app")

    parser = argparse.ArgumentParser(description="Python Trainer")
    parser.add_argument("--cli", action="store_true", help="Usar interfaz de consola")
    parser.add_argument("--exam", action="store_true", help="Iniciar en modo examen")
    args = parser.parse_args()

    if args.cli:
        logger.info("Modo seleccionado: CLI (exam=%s)", bool(args.exam))
        from ui.cli import run_app as run_cli
        run_cli(exam_mode=args.exam)
    else:
        logger.info("Modo seleccionado: GUI (exam=%s)", bool(args.exam))
        from ui.gui import run_app as run_gui
        run_gui(exam_mode=args.exam)


if __name__ == "__main__":
    main()
