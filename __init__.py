""" Insightly-LDAP synchronization module.

This module initializer holds common functions.
"""
import os
import json
from requests import post
from unidecode import unidecode


def sanitize(name):
    """Replace spaces and single quotes with other system-friendly characters, transliterate if necessary.

    Args:
        name (str): String to sanitize.

    Returns:
        str: The sanitized string.
    """
    return unidecode(name).replace(' ', '.').replace('\'', '_')


def fileToRedmine(key=None, subject=None, message=None, priority='normal'):
    """File an incident to Redmine.

    Args:
        key (str): Redmine REST API key.
        subject (str): Short description of the incident.
        message (str): Long description and extra details of the incident.
        priority (str): one of 'low', 'normal', 'high' or 'critical'.
    """

    message = message if message else ''
    _priority_ids = {
        'low': 1,
        'normal': 2,
        'high': 3,
        'critical': 4
    }
    issue = {
        'issue': {
            'project_id': 1,
            'tracker_id': 1,
            'assigned_to_id': 266,
            'priority_id': _priority_ids[priority.lower()],
            'subject': subject,
            'description': message + '\n\n- %s' % os.environ['HOSTNAME']
        }
    }

    post('https://support.forgeservicelab.fi/redmine/projects/digile/issues.json', data=json.dumps(issue),
         headers={'Content-type': 'application/json', 'X-Redmine-API-Key': key})
