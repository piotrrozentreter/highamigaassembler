"""guicreator - WYSIWYG GUI designer that emits HAS metadata for the 68000 pipeline.

The package is deliberately split so the metadata layer can be used headlessly
(CI, scripting) without importing Tkinter:

    model      - MetadataManager, WindowSpec, Control  (no GUI dependency)
    hasmeta    - .hasmeta writer/reader                 (no GUI dependency)
    has_export - .has skeleton emitter                  (no GUI dependency)
    builder    - Tkinter WYSIWYG editor
"""

from .model import (
    Control,
    ControlType,
    MetadataManager,
    WindowSpec,
)

__all__ = [
    "Control",
    "ControlType",
    "MetadataManager",
    "WindowSpec",
    "__version__",
]

__version__ = "1.0.0"
