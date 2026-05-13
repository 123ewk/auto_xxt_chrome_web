"""Template image management.

Each template is a PNG image file stored in this directory.
Templates are referenced by name from the main script config.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent


class Template:
    """Represents a template image with existence check."""

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def __str__(self) -> str:
        return str(self.path)


def load_templates() -> dict[str, Template]:
    """Load all template images from the templates directory.

    Returns:
        Dict mapping template name (without .png) to Template object.
    """
    templates: dict[str, Template] = {}
    mandatory = [
        "play_button",
        "next_section",
        "complete_checkmark",
        "task_complete",
        "back_to_course",
        "section_unlocked",
        "generic_next",
        "speed_2x",
        "speed_1.5x",
        "speed_1x",
        "mute_button",
        "popup_confirm",
        "popup_cancel",
        "popup_close",
        "quiz_option_a",
        "quiz_option_b",
        "quiz_option_c",
        "quiz_option_d",
        "quiz_confirm",
        "video_region",
    ]

    for name in mandatory:
        path = TEMPLATES_DIR / f"{name}.png"
        templates[name] = Template(name, path)

    return templates


def list_missing(templates: dict[str, Template]) -> list[str]:
    """Return names of templates that don't exist yet."""
    return [name for name, tpl in templates.items() if not tpl.exists()]


def print_status(templates: dict[str, Template]):
    """Print which templates are ready and which are missing."""
    existing = [n for n, t in templates.items() if t.exists()]
    missing = list_missing(templates)

    print(f"\nTemplates: {len(existing)} ready, {len(missing)} missing")
    if existing:
        print(f"  Ready: {', '.join(existing)}")
    if missing:
        print(f"  Missing: {', '.join(missing)}")
