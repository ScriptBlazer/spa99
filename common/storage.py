"""Static file storage: WhiteNoise's compressed manifest storage, plus hashed ES module imports.

Without `support_js_module_import_aggregation`, `app.<hash>.js` would still import `./feedback.js` by its
plain name, so browsers could keep an old cached module. With it, the imports point at hashed names.

`max_post_process_passes`: each pass can settle only one more step of an import chain when files come in an
unlucky order. Django's default is 5, but control.js imports through 8 files, so the image build failed on
Linux (it lists files in a different order than macOS). 2026-11-27. Keep it above the longest chain; the test
in common/tests/test_static_chain.py checks that.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class SpaStaticFilesStorage(CompressedManifestStaticFilesStorage):
    support_js_module_import_aggregation = True
    max_post_process_passes = 20
