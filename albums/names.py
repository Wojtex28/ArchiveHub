"""Płeć podpowiadana z imienia (ETAP 46). To tylko podpowiedź: każdą można poprawić w „Edytuj dane”.

Polskie imiona żeńskie prawie zawsze kończą się na „-a”, męskie nie. Wyjątki są na krótkich listach.
Przed imieniem bywa słowo rodzinne („babcia Helena”, „wujek Staszek”) i ono rozstrzyga pierwsze.
"""

FEMALE, MALE = "K", "M"

MALE_ON_A = {"kuba", "barnaba", "bonawentura", "kosma", "jarema", "dyzma", "juda", "ezra", "luca", "nikita"}
FEMALE_NOT_ON_A = {"beatrycze", "miriam", "noemi", "ruth", "rut", "nel", "karmen", "carmen", "ines", "ingrid"}
FAMILY_WORDS = {
    FEMALE: {"babcia", "babka", "prababcia", "ciocia", "ciotka", "mama", "matka", "siostra", "pani", "córka"},
    MALE: {"dziadek", "dziadzio", "pradziadek", "wujek", "wuj", "stryj", "stryjek", "tata", "ojciec", "brat"}
    | {"pan", "syn", "ksiądz", "ks."},
}


def guess_gender(name):
    """„K”, „M” albo pusty tekst, gdy z nazwy nic pewnego nie wynika."""
    for word in name.casefold().split():
        for gender, words in FAMILY_WORDS.items():
            if word in words:
                return gender
        word = word.strip(".,()\"'„”")
        if len(word) < 3 or not word.isalpha():
            continue
        if word in MALE_ON_A:
            return MALE
        if word in FEMALE_NOT_ON_A or word.endswith("a"):
            return FEMALE
        return MALE
    return ""
