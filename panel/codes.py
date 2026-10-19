import secrets

# Słowa bez polskich znaków, żeby kod dało się łatwo przepisać na każdym telefonie.
WORDS = (
    "lipa dab brzoza jablon wierzba sosna kasztan klon jarzebina malina czeresnia sliwka "
    "gruszka lawenda rumianek mak chaber bocian wrobel sikorka skowronek jaskolka kos "
    "rzeka potok laka sad ogrod ganek strych kredens fotel zegar latarnia most mlyn "
    "kompot powidla pierniki kolacz bulka miod ksiezyc gwiazda tecza obloczek"
).split()


def suggest_code():
    """Propozycja kodu rodzinnego, np. „lipa-bocian-64”."""
    first, second = secrets.choice(WORDS), secrets.choice(WORDS)
    while second == first:
        second = secrets.choice(WORDS)
    return f"{first}-{second}-{secrets.randbelow(90) + 10}"
