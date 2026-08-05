"""
Geo classifier for Facebook groups.
Detects likely country/location from group names using keyword heuristics.
"""

import logging

logger = logging.getLogger(__name__)


class GeoClassifier:
    COUNTRY_PATTERNS = {
        "germany": {
            "flag": "🇩🇪",
            "label": "Germany",
            "keywords": [
                "deutschland", "germany", "berlin", "берлин", "берлине", "hamburg", "гамбург", "münchen", "munich",
                "frankfurt", "köln", "cologne", "stuttgart", "düsseldorf", "dortmund",
                "leipzig", "essen", "hannover", "deutsch", "deutsche"
            ],
        },
        "switzerland": {
            "flag": "🇨🇭",
            "label": "Switzerland",
            "keywords": [
                "schweiz", "switzerland", "zürich", "zurich", "bern", "basel", "genf",
                "geneva", "lausanne", "winterthur", "st. gallen", "lugano", "lucerne",
                "luzern"
            ],
        },
        "austria": {
            "flag": "🇦🇹",
            "label": "Austria",
            "keywords": [
                "österreich", "austria", "wien", "vienna", "graz", "linz", "salzburg",
                "innsbruck", "klagenfurt"
            ],
        },
        "poland": {
            "flag": "🇵🇱",
            "label": "Poland",
            "keywords": [
                "polska", "poland", "warszawa", "warsaw", "kraków", "krakow", "gdańsk",
                "gdansk", "wrocław", "wroclaw", "poznań", "poznan", "łódź", "lodz",
                "katowice"
            ],
        },
        "ukraine": {
            "flag": "🇺🇦",
            "label": "Ukraine",
            "keywords": [
                "україна", "украина", "ukraine", "kyiv", "київ", "киев", "львів", "львов",
                "odesa", "одеса", "одесса", "харків", "харьков", "дніпро", "днепр",
                "zaporizhzhia", "запоріжжя", "запорожье"
            ],
        },
        "russia": {
            "flag": "🇷🇺",
            "label": "Russia",
            "keywords": [
                "россия", "russia", "москва", "moscow", "петербург", "saint petersburg",
                "спб", "екатеринбург", "novosibirsk", "новосибирск", "казань", "kazan"
            ],
        },
        "france": {
            "flag": "🇫🇷",
            "label": "France",
            "keywords": [
                "france", "paris", "lyon", "marseille", "toulouse", "nice", "français",
                "francaise"
            ],
        },
        "italy": {
            "flag": "🇮🇹",
            "label": "Italy",
            "keywords": [
                "italy", "italia", "roma", "rome", "milano", "milan", "napoli",
                "naples", "torino", "turin", "bologna"
            ],
        },
        "spain": {
            "flag": "🇪🇸",
            "label": "Spain",
            "keywords": [
                "spain", "españa", "espana", "madrid", "barcelona", "valencia",
                "sevilla", "malaga"
            ],
        },
        "netherlands": {
            "flag": "🇳🇱",
            "label": "Netherlands",
            "keywords": [
                "netherlands", "nederland", "amsterdam", "rotterdam", "utrecht",
                "den haag", "the hague", "eindhoven"
            ],
        },
        "belgium": {
            "flag": "🇧🇪",
            "label": "Belgium",
            "keywords": [
                "belgium", "belgië", "belgie", "brussels", "bruxelles", "antwerp",
                "gent", "ghent", "brugge", "liege"
            ],
        },
        "united_kingdom": {
            "flag": "🇬🇧",
            "label": "United Kingdom",
            "keywords": [
                "uk ", "united kingdom", "england", "london", "manchester", "birmingham",
                "liverpool", "glasgow", "edinburgh", "bristol"
            ],
        },
        "usa": {
            "flag": "🇺🇸",
            "label": "USA",
            "keywords": [
                "usa", "united states", "america", "new york", "los angeles", "chicago",
                "miami", "houston", "dallas", "san francisco", "california", "texas"
            ],
        },
        "canada": {
            "flag": "🇨🇦",
            "label": "Canada",
            "keywords": [
                "canada", "toronto", "montreal", "vancouver", "calgary", "ottawa",
                "quebec"
            ],
        },
    }

    @classmethod
    def classify_group(cls, group_name: str) -> str:
        if not group_name:
            return "unknown"
        name_lower = f" {group_name.lower()} "
        scores = {}
        for country_code, config in cls.COUNTRY_PATTERNS.items():
            score = 0
            for keyword in config["keywords"]:
                if keyword.lower() in name_lower:
                    score += len(keyword) + 3
            if score:
                scores[country_code] = score
        return max(scores, key=scores.get) if scores else "unknown"

    @classmethod
    def get_country_info(cls, country_code: str):
        if country_code in cls.COUNTRY_PATTERNS:
            config = cls.COUNTRY_PATTERNS[country_code]
            return {
                "code": country_code,
                "name": config["label"],
                "flag": config["flag"],
            }
        return {"code": "unknown", "name": "Unknown", "flag": "❓"}

    @classmethod
    def classify_groups_batch(cls, groups):
        classified_groups = []
        stats = {}
        for group in groups:
            item = group.copy()
            country = cls.classify_group(group.get("name", ""))
            info = cls.get_country_info(country)
            item["country_tag"] = country
            item["country_name"] = info["name"]
            item["country_flag"] = info["flag"]
            stats[country] = stats.get(country, 0) + 1
            classified_groups.append(item)

        logger.info("Geo classification completed:")
        for country, count in sorted(stats.items()):
            info = cls.get_country_info(country)
            logger.info(f"  {info['flag']} {info['name']}: {count} groups")
        return classified_groups
