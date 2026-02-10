import sys

from main import main


if __name__ == "__main__":
    if "--cli" not in sys.argv:
        sys.argv.append("--cli")
    main()
