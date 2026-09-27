"""Verify local assets/navigation and keep the prelaunch website free of intake forms."""
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SiteParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.anchors, self.assets, self.forms = set(), [], [], []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            assert attributes["id"] not in self.ids, "Duplicate page ID"
            self.ids.add(attributes["id"])
        for key in ("src", "href"):
            value = attributes.get(key, "")
            if value.startswith("#"):
                self.anchors.append(value[1:])
            elif value and not value.startswith(("http:", "https:", "data:", "tel:")):
                self.assets.append(value)
        if tag in ("form", "input", "textarea"):
            self.forms.append(tag)
        if tag == "img":
            assert "alt" in attributes, "Image missing alt attribute"


def main():
    parser = SiteParser()
    parser.feed((ROOT / "site/index.html").read_text())
    assert all(anchor in parser.ids for anchor in parser.anchors), "Broken anchor"
    assert all((ROOT / "site" / asset).is_file() for asset in parser.assets), "Missing asset"
    assert not parser.forms, "Prelaunch site must not collect patient information"
    print("Site assets, navigation, image labels, and prelaunch state verified.")


if __name__ == "__main__":
    main()
