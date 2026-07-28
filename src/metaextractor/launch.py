"""Console-script entry point that starts the Streamlit web app.

``streamlit run`` needs a script path, so this shells out to it pointing at
``webapp.py``. Extra CLI args are forwarded to Streamlit, e.g.::

    metaextract-app --server.port 8502
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        from streamlit.web import cli as stcli
    except ImportError:
        sys.stderr.write(
            "The web app requires the 'app' extra: pip install 'metaextractor[app]'\n"
        )
        return 1
    app_path = str(Path(__file__).with_name("webapp.py"))
    sys.argv = ["streamlit", "run", app_path, *argv]
    return int(stcli.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
