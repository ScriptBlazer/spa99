"""Short, shareable codes people can read out loud (ACC-05)."""
import re
import secrets

# No 0/O, 1/I/L or U: nothing that looks like something else.
UNAMBIGUOUS_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
PUBLIC_CODE_LENGTH = 8


def generate_public_code(length=PUBLIC_CODE_LENGTH):
    return "".join(secrets.choice(UNAMBIGUOUS_ALPHABET) for _ in range(length))


def normalise_public_code(text):
    """'abcd-efgh ' -> 'ABCDEFGH'. Does not validate."""
    return re.sub(r"[\s-]", "", text or "").upper()


def format_public_code(code):
    """'ABCDEFGH' -> 'ABCD-EFGH'."""
    return f"{code[:4]}-{code[4:]}" if len(code) > 4 else code
