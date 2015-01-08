"""Check OpenStack tenants' quotas."""
from __init__ import sanitize
from swiftclient import service as switfService
from cinderclient.v2 import client as cinderClient
from neutronclient.v2_0 import client as neutronClient
from novaclient.v1_1 import client as novaClient
from novaclient.exceptions import Conflict, NotFound
from ldap_updater import LDAPUpdater


class QuotaChecker:

    """Check and enforce OpenStack tenant quota.

    Verifies that a given tenant does have its correct allocated quota.

    Attributes:
        DEFAULT_QUOTA (dict): The default quota for a service developer.
        PARTNER_QUOTA (dict): The default quota for a partner with CRA.
        BIGDATA_QUOTA (dict): The quota for big data enabled projects.
    """

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

    def __init__(self, username=None, password=None, tenantid=None):
        """Set instance authentication constants.

        Args:
            username (str): OpenStack administrator username.
            password (str): OpenStack administrator password.
            tenantid (str): OpenStack tenant for the administrator account.
        """
        self._AUTH_USERNAME = username
        self._AUTH_PASSWORD = password
        self._AUTH_TENANTID = tenantid

    def _getTenantQuota(self, tenant, tenantType):
        quota = None
        statedQuota = map(lambda q: q['FIELD_VALUE'], filter(lambda f: f['CUSTOM_FIELD_ID'] == 'PROJECT_FIELD_1',
                                                             tenant['CUSTOMFIELDS']))
        if statedQuota == self._BIGDATA_QUOTA_NAME:
            quota = self.BIGDATA_QUOTA
        else:
            if statedQuota == self._DEFAULT_QUOTA_NAME:
                if tenantType == LDAPUpdater.FPA_CRA:
                    quota = self.PARTNER_QUOTA
                if tenantType == LDAPUpdater.SDA:
                    quota = self.DEFAULT_QUOTA

        return quota

    def _grantAccess(self, client, flavor, tenant):
        try:
            client.flavor_access.add_tenant_access(flavor, tenant)
        except Conflict:
            pass

    def _revokeAccess(self, client, flavor, tenant):
        try:
            client.flavor_access.remove_tenant_access(flavor, tenant)
        except NotFound:
            pass

    def _enforceQuota(self, tenant, quotaDefinition):
        # TODO: remove return statement.
        return
        if quotaDefinition:
            service_opts = {
                'meta': ['quota-bytes:%s' % quotaDefinition['swift_bytes']],
                'os_username': self._AUTH_USERNAME,
                'os_password': self._AUTH_PASSWORD,
                'os_auth_url': 'https://cloud.forgeservicelab.fi:5001/v2.0',
                'os_storage_url': 'https://cloud.forgeservicelab.fi:8081/v1/AUTH_digile',
                'os_tenant_name': tenant
            }

            swift = switfService.SwiftService(options=service_opts)
            swift.post()

            cinder = cinderClient.Client(username=self._AUTH_USERNAME,
                                         api_key=self._AUTH_PASSWORD,
                                         tenant_id=self._AUTH_TENANTID,
                                         auth_url=service_opts['os_auth_url'])
            cinder.quotas.update(tenant, gigabytes=quotaDefinition['cinder_GB'])

            nova = novaClient.Client(username=self._AUTH_USERNAME,
                                     api_key=self._AUTH_PASSWORD,
                                     tenant_id=self._AUTH_TENANTID,
                                     auth_url=service_opts['os_auth_url'])
            nova.quotas.update(tenant,
                               instances=quotaDefinition['instances'],
                               cores=quotaDefinition['cores'],
                               ram=quotaDefinition['ram'],
                               floating_ips=quotaDefinition['floating_ips'])
            allFlavors = nova.flavors.findall()
            map(lambda f: self._grantAccess(nova, f, tenant),
                filter(lambda f: f.name.encode() in quotaDefinition['flavors'], allFlavors))
            map(lambda f: self._revokeAccess(nova, f, tenant),
                filter(lambda f: f.name.encode() not in quotaDefinition['flavors'], allFlavors))

            neutron = neutronClient.Client(username=self._AUTH_USERNAME,
                                           password=self._AUTH_PASSWORD,
                                           tenant_id=self._AUTH_TENANTID,
                                           auth_url=service_opts['os_auth_url'])
            neutron.update_quota(tenant, {'quota': {'floatingip': quotaDefinition['floating_ips']}})

    def enforceQuotas(self, tenantList, tenantsType):
        """Enforce the quota for each tenant on the list.

        Args:
            tenantList (List): A list of tenants as JSON from Insightly.
            tenantsType (str): A description of the type of tenant, one of 'SDA', 'FPA' or 'FPA (CRA)'.
        """
        map(lambda t: self._enforceQuota(sanitize(t['PROJECT_NAME']),
                                         self._getTenantQuota(t, tenantsType)), tenantList)
