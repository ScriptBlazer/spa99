"""Static file storage: WhiteNoise's compressed manifest storage, plus hashed ES module imports.

Without `support_js_module_import_aggregation`, `app.<hash>.js` would still import `./modal.js` by its
plain name, so browsers could keep an old cached module. With it, the imports point at hashed names.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class SpaStaticFilesStorage(CompressedManifestStaticFilesStorage):
    support_js_module_import_aggregation = True
