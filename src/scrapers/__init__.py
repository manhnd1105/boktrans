from .truyenfull import TruyenfullScraper
from .zingtruyen import ZingtruyenScraper

_SCRAPERS = {
    "truyenfull.vision": TruyenfullScraper,
    "zingtruyen.store": ZingtruyenScraper,
}


def detect_scraper(url: str):
    for domain, cls in _SCRAPERS.items():
        if domain in url:
            return cls()
    supported = ", ".join(_SCRAPERS)
    raise ValueError(f"Unsupported site. Supported: {supported}")
