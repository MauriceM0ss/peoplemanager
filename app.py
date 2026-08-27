"""Entrypoint for the People Manager app.

The implementation lives in the ``peoplecrm`` package (app factory +
blueprints); this module exposes ``app`` for the Docker entrypoint
(``python app.py``) and re-exports a few helpers used by the test suite.
"""
from peoplecrm import create_app
from peoplecrm.config import DB_PATH, _PIN_CONFIG  # noqa: F401  (re-exported)
from peoplecrm.db import init_db  # noqa: F401  (re-exported)
from peoplecrm.helpers import (  # noqa: F401  (re-exported)
    doc_icon, experience_display, format_years, human_size, normalize_id,
    pretty_date, stable_hash, whole_years_since,
)
from peoplecrm.security import (  # noqa: F401  (re-exported)
    _derive_key, _load_pin_config,
)

app = create_app()


if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _load_pin_config() is None:
        init_db()
    app.run(host="0.0.0.0", port=8080, debug=False)
