"""Check OpenStack tenants' quotas.

Verifies that a given tenant does have its correct allocated quota.

Attributes:
    DEFAULT_QUOTA (dict): The default quota for a service developer.
    PARTNER_QUOTA (dict): The default quota for a partner with CRA.
    BIGDATA_QUOTA (dict): The quota for big data enabled projects.
"""
from swiftclient import service as switfService
from cinderclient.v2 import client as cinderClient
from neutronclient.v2_0 import client as neutronClient
from novaclient.v1_1 import client as novaClient
from novaclient.exceptions import Conflict, NotFound
from ldap_updater import SDA, FPA_CRA
from ldapsync import sanitize

_AUTH_USERNAME = 
_AUTH_PASSWORD = 
_AUTH_TENANTID = 

_DEFAULT_QUOTA_NAME = 'Default CRA quota'
_BIGDATA_QUOTA_NAME = 'Bigdata CRA quota'

DEFAULT_QUOTA = {
    'instances': 16,
    'cores': 16,
    'ram': 32 * 1024,
    'floating_ips': 5,
    'cinder_GB': 1024,
    'swift_bytes': 1024 * 1024 * 1024 * 1024,
    'flavors': ['m1.tiny', 'm1.small', 'm1.medium', 'm1.large', 'm1.x-large']
}

PARTNER_QUOTA = {
    'instances': 1,
    'cores': 1,
    'ram': 1024,
    'floating_ips': 1,
    'cinder_GB': 40,
    'swift_bytes': 40 * 1024 * 1024 * 1024,
    'flavors': ['m1.tiny']
}

BIGDATA_QUOTA = {
    'instances': 16,
    'cores': 46,
    'ram': 400 * 1024,
    'floating_ips': 15,
    'cinder_GB': 1024,
    'swift_bytes': 1024 * 1024 * 1024 * 1024,
    'flavors': ['m1.tiny', 'm1.small', 'hadoop.small', 'hadoop.medium', 'hadoop.large']
}


# ## Experimental excerpts ## #
def _getTenantQuota(tenant, tenantType):
    quota = None
    statedQuota = map(lambda q: q['FIELD_VALUE'], filter(lambda f: f['CUSTOM_FIELD_ID'] == 'PROJECT_FIELD_1',
                                                         tenant['CUSTOMFIELDS']))
    if statedQuota == _BIGDATA_QUOTA_NAME:
        quota = BIGDATA_QUOTA
    else:
        if statedQuota == _DEFAULT_QUOTA_NAME:
            if tenantType == FPA_CRA:
                quota = PARTNER_QUOTA
            if tenantType == SDA:
                quota = DEFAULT_QUOTA

    return quota


def _grantAccess(client, flavor, tenant):
    try:
        client.flavor_access.add_tenant_access(flavor, tenant)
    except Conflict:
        pass


def _revokeAccess(client, flavor, tenant):
    try:
        client.flavor_access.remove_tenant_access(flavor, tenant)
    except NotFound:
        pass


def _enforceQuota(tenant, quotaDefinition):
    # TODO: remove return statement.
    return
    if quotaDefinition:
        service_opts = {
            'meta': ['quota-bytes:%s' % quotaDefinition['swift_bytes']],
            'os_username': _AUTH_USERNAME,
            'os_password': _AUTH_PASSWORD,
            'os_auth_url': 'https://cloud.forgeservicelab.fi:5001/v2.0',
            'os_storage_url': 'https://cloud.forgeservicelab.fi:8081/v1/AUTH_digile',
            'os_tenant_name': tenant
        }

        swift = switfService.SwiftService(options=service_opts)
        swift.post()

        cinder = cinderClient.Client(username=_AUTH_USERNAME,
                                     api_key=_AUTH_PASSWORD,
                                     tenant_id=_AUTH_TENANTID,
                                     auth_url=service_opts['os_auth_url'])
        cinder.quotas.update(tenant, gigabytes=quotaDefinition['cinder_GB'])

        nova = novaClient.Client(username=_AUTH_USERNAME,
                                 api_key=_AUTH_PASSWORD,
                                 tenant_id=_AUTH_TENANTID,
                                 auth_url=service_opts['os_auth_url'])
        nova.quotas.update(tenant,
                           instances=quotaDefinition['instances'],
                           cores=quotaDefinition['cores'],
                           ram=quotaDefinition['ram'],
                           floating_ips=quotaDefinition['floating_ips'])
        allFlavors = nova.flavors.findall()
        map(lambda f: _grantAccess(nova, f, tenant),
            filter(lambda f: f.name.encode() in quotaDefinition['flavors'], allFlavors))
        map(lambda f: _revokeAccess(nova, f, tenant),
            filter(lambda f: f.name.encode() not in quotaDefinition['flavors'], allFlavors))

        neutron = neutronClient.Client(username=_AUTH_USERNAME,
                                       password=_AUTH_PASSWORD,
                                       tenant_id=_AUTH_TENANTID,
                                       auth_url=service_opts['os_auth_url'])
        neutron.update_quota(tenant, {'quota': {'floatingip': quotaDefinition['floating_ips']}})


def enforceQuotas(tenantList, tenantsType):
    map(lambda t: _enforceQuota(sanitize(t['PROJECT_NAME']), _getTenantQuota(t, tenantsType)), tenantList)
