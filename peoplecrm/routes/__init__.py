"""Route blueprints."""
from . import auth, data, files, pages, records

BLUEPRINTS = (auth.bp, pages.bp, records.bp, files.bp, data.bp)
