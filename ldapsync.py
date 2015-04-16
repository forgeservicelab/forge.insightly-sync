#!/usr/bin/env python
"""Fetch identity data from Insightly and synchronize it with LDAP.

Usage:
    ldapsync.py [-l <ldap_host>] -b <ldap_bind_cn> -p <ldap_bind_pwd> -i <insightly_api_key> -U <os_user> -P <os_pass>\
 -T <os_tenant> [-v <log_level>] [-R <redmine_api_key>] [-O <os_base_url>]
    ldapsync.py -r <identity_file> [-v <log_level>]
    ldapsync.py -h | --help

Options:
    -h --help                           Show this screen.
    -i --api_key <insightly_api_key>    Insightly API key.
    -l --ldap <ldap_host>               LDAP host to connect to [default: localhost].
    -b --bind <ldap_bind_cn>            Username of the LDAP account for binding (needs admin rights).
    -p --password <ldap_bind_pwd>       LDAP binding account password.
    -U --os_user <os_user>              OpenStack administrator username.
    -P --os_pass <os_pass>              OpenStack administrator password.
    -T --os_tenant <os_tenant>          OpenStack tenant for administrator account.
    -O --os_base_url <os_base_url>      URI of the OpenStack environment. [default: https://cloud.forgeservicelab.fi]
    -R --redmine_api <redmine_api_key>  Redmine REST API key.
    -r --resources <identity_file>      A file with the identity resources in the format [long_option_name]=[value].
    -v --verbose <log_level>            Verbose level, one of DEBUG, INFO, WARNING, ERROR, CRITICAL [default: WARNING]
"""
import logging
import traceback
from __init__ import sanitize, fileToRedmine
from fuzzywuzzy import process
from insightly_updater import InsightlyUpdater
from ldap_updater import LDAPUpdater, ForgeLDAP
from quota_checker import QuotaChecker
from requests import get
from docopt import docopt
from time import sleep

TECH_ROLE = 'tech'
ADMIN_ROLE = 'admin'


def filterStagesByOrder(stage_order_list, stage_list, pipeline_list):
    """Return a list of Insightly pipeline stage IDs based on their order.

    Filter the pipeline_list parameter to keep only pipelines matching PIPELINE_NAME.
    Filter the stage_list parameter to keep only stages belonging to the filtered pipeline_list.
    Filter the subset of stages that belong to the filtered pipeline list to keep only those with an order in the
    stage_order_list parameter.

    Args:
        stage_order_list (List): List of orders to keep after filtering.
        stage_list (List): Complete list of stages to filter by order.
        pipeline_list: Complete list of pipelines to filter by name.

    Returns:
        List: The relevant stage IDs that matched the ordering criteria.
    """
    return map(lambda cs: cs['STAGE_ID'],
               filter(lambda s: s['PIPELINE_ID'] in map(lambda p: p['PIPELINE_ID'],
                                                        filter(lambda q: q['PIPELINE_NAME'] in [LU.PIPELINE_NAME],
                                                               pipeline_list)) and
                      s['STAGE_ORDER'] in stage_order_list, stage_list
                      )
               )


def mapContactsToLDAP(contact_list):
    """Create a payload for ldap_updater module calls.

    Generate a list of dictionaries mapping Insightly properties to LDAP attributes.

    Args:
        contact_list (List): A list of contacts as JSON from Insightly to be converted into LDAP-like dictionaries.

    Returns:
        List: The contact list converted into dictionaries with the relevant LDAP attributes.
    """
    return map(lambda c: {'employeeNumber': str(c['CONTACT_ID']),
                          'givenName': c['FIRST_NAME'].encode('utf-8') if c['FIRST_NAME'] else '',
                          'sn': c['LAST_NAME'].encode('utf-8') if c['LAST_NAME'] else '',
                          'displayName': ('%s %s' % (c['FIRST_NAME'], c['LAST_NAME'])).strip().encode('utf-8'),
                          'mail': map(lambda m: m['DETAIL'].encode('utf-8'),
                                      filter(lambda e: e['TYPE'] == 'EMAIL', c['CONTACTINFOS'])),
                          'mobile': map(lambda m: m['DETAIL'].encode('utf-8'),
                                        filter(lambda e: e['TYPE'] == 'PHONE', c['CONTACTINFOS'])),
                          'isHidden': map(lambda t: t['FIELD_VALUE'],
                                          filter(lambda f: f['CUSTOM_FIELD_ID'] == 'CONTACT_FIELD_1',
                                                 c['CUSTOMFIELDS'])),
                          }, contact_list) if contact_list else []


def mapProjectsToLDAP(project_list, project_type, tenant_list=False):
    """Create a payload for ldap_updater module calls.

    Generate a list of dictionaries mapping Insightly properties to LDAP attributes.

    Args:
        project_list (List): A list of projects as JSON from Insightly to be converted into LDAP-like dictionaries.
        project_type (List): A description of the type of project, one of 'SDA', 'FPA' or 'FPA (CRA)'.
        tenant_list (List, optional): A list of tenants as JSON from Insightly,
            i.e. projects on the 'OpenStack Tenant' category.

    Returns:
        List: The project list converted into dictionaries with the relevant LDAP attributes, including nested tenants.
    """
    return map(lambda p: {'o': str(p['PROJECT_ID']),
                          'description': project_type,
                          'cn': sanitize(p['PROJECT_NAME']),
                          'owner': mapContactsToLDAP(filter(lambda owner: owner['CONTACT_ID'] in
                                                            map(lambda c: c['CONTACT_ID'],
                                                                filter(lambda o:
                                                                       o['CONTACT_ID'] is not None and
                                                                       process.extractOne(
                                                                           TECH_ROLE,
                                                                           [str(o['ROLE'])],
                                                                           score_cutoff=80),
                                                                       p['LINKS'])), USERS)
                                                     )[:1],
                          'seeAlso': mapContactsToLDAP(filter(lambda admin: admin['CONTACT_ID'] in
                                                              map(lambda c: c['CONTACT_ID'],
                                                                  filter(lambda a:
                                                                         a['CONTACT_ID'] is not None and
                                                                         process.extractOne(
                                                                             ADMIN_ROLE,
                                                                             [str(a['ROLE'])],
                                                                             score_cutoff=80),
                                                                         p['LINKS'])), USERS)
                                                       ),
                          'member': mapContactsToLDAP(filter(lambda member: member['CONTACT_ID'] in
                                                             map(lambda c: c['CONTACT_ID'],
                                                                 filter(lambda m:
                                                                        m[
                                                                            'CONTACT_ID'] is not None,
                                                                        p['LINKS'])), USERS)
                                                      ),
                          'tenants': mapProjectsToLDAP(filter(lambda t:
                                                              t['PROJECT_ID'] in
                                                              map(lambda sp:
                                                                  sp['SECOND_PROJECT_ID'],
                                                                  filter(lambda l:
                                                                         l[
                                                                             'SECOND_PROJECT_ID'] is not None,
                                                                         p['LINKS'])),
                                                              tenant_list),
                                                       project_type + [LU.OS_TENANT]) if tenant_list else [],
                          }, project_list) if project_list else []


def _retry_get_request(uri, **kwargs):
    response = get(uri, **kwargs)
    while response.status_code is not 200:
        sleep(0.1)
        response = get(uri, **kwargs)
    return response


if __name__ == '__main__':
    arguments = docopt(__doc__)
    logging.basicConfig(filename='/var/log/insightly_sync.log',
                        format='%(asctime)s - [%(name)s] %(levelname)s: %(message)s',
                        level=arguments['--verbose'].upper())
    try:
        if arguments['--resources']:
            identity_file = file(arguments['--resources'], 'r')
            map(lambda a: arguments.update(
                [('--' + a.strip()).split('=')]), identity_file.readlines())
            identity_file.close()

        IU = InsightlyUpdater(api_key=arguments['--api_key'],
                              stages=_retry_get_request(InsightlyUpdater.INSIGHTLY_PIPELINE_STAGES_URI,
                                                        auth=(arguments['--api_key'], '')).json(),
                              tenant_category=map(lambda t: t['CATEGORY_ID'],
                                                  filter(lambda c: c['CATEGORY_NAME'] == 'OpenStack Tenant',
                                                         _retry_get_request(InsightlyUpdater.INSIGHTLY_CATEGORIES_URI,
                                                                            auth=(arguments['--api_key'],
                                                                                  '')).json()))[0])
        LU = LDAPUpdater(IU)
        QC = QuotaChecker(username=arguments['--os_user'], password=arguments['--os_pass'],
                          tenantid=arguments['--os_tenant'], baseurl=arguments['--os_base_url'])

        PIPELINES = filter(lambda p: p['PIPELINE_NAME'] in [LU.PIPELINE_NAME],
                           _retry_get_request(IU.INSIGHTLY_PIPELINES_URI,
                                              auth=(IU.INSIGHTLY_API_KEY, '')).json()
                           )

        PROJ_CATEGORIES = dict(map(lambda pc: (pc['CATEGORY_NAME'], pc['CATEGORY_ID']),
                                   filter(lambda c: c['CATEGORY_NAME'] in [LU.SDA, LU.FPA, LU.FPA_CRA, LU.OS_TENANT],
                                          _retry_get_request(IU.INSIGHTLY_CATEGORIES_URI,
                                                             auth=(IU.INSIGHTLY_API_KEY, '')).json())))

        PROJECTS = _retry_get_request(IU.INSIGHTLY_PROJECTS_URI, auth=(IU.INSIGHTLY_API_KEY, '')).json()
        USERS = _retry_get_request(IU.INSIGHTLY_CONTACTS_URI, auth=(IU.INSIGHTLY_API_KEY, '')).json()

        TENANTS = filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.OS_TENANT], PROJECTS)

        creation_stages = filterStagesByOrder([4], IU.STAGES, PIPELINES)
        update_stages = filterStagesByOrder([5, 6], IU.STAGES, PIPELINES)
        deletion_stages = filterStagesByOrder([7], IU.STAGES, PIPELINES)

        # Filter projects by relevant pipeline stages.
        projects_to_be_created = filter(lambda p: p['CATEGORY_ID'] in PROJ_CATEGORIES.values() and
                                        p['STAGE_ID'] in creation_stages, PROJECTS)
        projects_to_be_updated = filter(lambda p: p['CATEGORY_ID'] in PROJ_CATEGORIES.values() and
                                        p['STAGE_ID'] in update_stages, PROJECTS)
        projects_to_be_deleted = filter(lambda p: p['CATEGORY_ID'] in PROJ_CATEGORIES.values() and
                                        p['STAGE_ID'] in deletion_stages and
                                        p['STATUS'] is not IU.STATUS_COMPLETED,
                                        PROJECTS)

        creation = {
            LU.SDA: mapProjectsToLDAP(filter(lambda p:
                                             p['CATEGORY_ID'] == PROJ_CATEGORIES[
                                                 LU.SDA],
                                             projects_to_be_created),
                                      [LU.SDA], tenant_list=TENANTS),
            LU.FPA_CRA: mapProjectsToLDAP(filter(lambda p:
                                                 p['CATEGORY_ID'] == PROJ_CATEGORIES[
                                                     LU.FPA_CRA],
                                                 projects_to_be_created),
                                          [LU.FPA_CRA], tenant_list=TENANTS),
            LU.FPA: mapProjectsToLDAP(filter(lambda p:
                                             p['CATEGORY_ID'] == PROJ_CATEGORIES[
                                                 LU.FPA],
                                             projects_to_be_created),
                                      [LU.FPA])
        }

        update = {
            LU.SDA: mapProjectsToLDAP(filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.SDA],
                                             projects_to_be_updated),
                                      [LU.SDA], tenant_list=TENANTS),
            LU.FPA_CRA: mapProjectsToLDAP(filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.FPA_CRA],
                                                 projects_to_be_updated),
                                          [LU.FPA_CRA], tenant_list=TENANTS),
            LU.FPA: mapProjectsToLDAP(filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.FPA],
                                             projects_to_be_updated),
                                      [LU.FPA])
        }

        deletion = {
            LU.SDA: mapProjectsToLDAP(filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.SDA],
                                             projects_to_be_deleted),
                                      [LU.SDA], tenant_list=TENANTS),
            LU.FPA_CRA: mapProjectsToLDAP(filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.FPA_CRA],
                                                 projects_to_be_deleted),
                                          [LU.FPA_CRA], tenant_list=TENANTS),
            LU.FPA: mapProjectsToLDAP(filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.FPA],
                                             projects_to_be_deleted),
                                      [LU.FPA])
        }

        ldap_connection = ForgeLDAP(arguments['--bind'], arguments['--password'],
                                    arguments['--ldap'], arguments['--redmine_api'])

        LU.Action(LU.ACTION_CREATE, creation, ldap_connection)
        LU.Action(LU.ACTION_UPDATE, update, ldap_connection)
        LU.Action(LU.ACTION_DELETE, deletion, ldap_connection)

        QC.enforceQuotas(filter(lambda p: p['PROJECT_ID'] in
                                filter(lambda tp: tp,
                                       map(lambda t: t['SECOND_PROJECT_ID'],
                                           [link for sublist in
                                            map(lambda p: p['LINKS'],
                                                filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.SDA],
                                                       PROJECTS))
                                            for link in sublist])),
                                PROJECTS), LU.SDA, ldap_connection)

        QC.enforceQuotas(filter(lambda p: p['PROJECT_ID'] in
                                filter(lambda tp: tp,
                                       map(lambda t: t['SECOND_PROJECT_ID'],
                                           [link for sublist in
                                            map(lambda p: p['LINKS'],
                                                filter(lambda p: p['CATEGORY_ID'] == PROJ_CATEGORIES[LU.FPA_CRA],
                                                       PROJECTS))
                                            for link in sublist])),
                                PROJECTS), LU.FPA_CRA, ldap_connection)
    except Exception, err:
        logger = logging.getLogger(__name__)
        logger.exception(err)

        if arguments['--redmine_api']:
            fileToRedmine(key=arguments['--redmine_api'], subject=err.__class__.__name__,
                          message=traceback.format_exc(), priority='critical')
