""" Insightly-LDAP synchronization module.

This module initializer holds common functions.
"""
from unidecode import unidecode


def sanitize(name):
    """Replace spaces and single quotes with other system-friendly characters, transliterate if necessary.

    Args:
        name (str): String to sanitize.

    Returns:
        str: The sanitized string.
    """
    return unidecode(name).replace(' ', '.').replace('\'', '_')
