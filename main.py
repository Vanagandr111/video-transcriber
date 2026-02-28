import sys
import traceback

from app.config import get_paths, setup_runtime_paths
from app.ui import run_app


if __name__ == "__main__":
    paths = get_paths()
    setup_runtime_paths(paths.base_dir)
    log_file = paths.base_dir / "error.log"

    def _global_excepthook(exc_type, exc_value, exc_tb):
        error_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(error_text + "\n")
        except OSError:
            pass

    sys.excepthook = _global_excepthook
    run_app(paths)
