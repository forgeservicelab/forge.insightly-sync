"""Check OpenStack tenants' quotas."""
from __init__ import sanitize
from time import sleep
from ldap import SCOPE_SUBORDINATE
from swiftclient import service as switfService
from cinderclient.v2 import client as cinderClient
from keystoneclient.exceptions import NotFound
from keystoneclient.v3 import client as keystoneClient
from keystoneclient.v3.roles import RoleManager
from keystoneclient.v3.groups import GroupManager
from keystoneclient.v3.domains import DomainManager
from keystoneclient.v3.projects import ProjectManager
from keystoneclient.v3.role_assignments import RoleAssignmentManager
from neutronclient.v2_0 import client as neutronClient
from novaclient.v1_1 import client as novaClient
from novaclient.exceptions import Conflict
from novaclient.exceptions import NotFound
from novaclient.exceptions import BadRequest
from novaclient.exceptions import Unauthorized
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

    def __init__(self, username=None, password=None, tenantid=None, baseurl=None):
        """Set instance authentication constants.

        Args:
            username (str): OpenStack administrator username.
            password (str): OpenStack administrator password.
            tenantid (str): OpenStack tenant for the administrator account.
            baseurl  (str): OpenStack environment URI.
        """
        self._AUTH_USERNAME = username
        self._AUTH_PASSWORD = password
        self._AUTH_TENANTID = tenantid
        self._BASE_URL = baseurl
        keystone = keystoneClient.Client(username=self._AUTH_USERNAME,
                                         password=self._AUTH_PASSWORD,
                                         project_name=self._AUTH_TENANTID,
                                         auth_url='%s:5001/v3' % self._BASE_URL)
        self._roleManager = RoleManager(keystone)
        self._groupManager = GroupManager(keystone)
        self._domainManager = DomainManager(keystone)
        self._projectManager = ProjectManager(keystone)
        self._roleAssignmentManager = RoleAssignmentManager(keystone)

    def _getOpenstackGroup(self, group):
        try:
            return self._groupManager.find(name=group)
        except NotFound:
            return None

    def _getTenantId(self, tenant):
        projectMap = dict(map(lambda assignment: (assignment.group['id'], assignment.scope['project']['id']),
                                 filter(lambda a: 'group' in a._info.keys(), self._roleAssignmentManager.list())))

        return projectMap[tenant].strip() if projectMap.has_key(tenant) else None

    def _ensureTenantNetwork(self, tenant):
        neutron = neutronClient.Client(username=self._AUTH_USERNAME,
                                       password=self._AUTH_PASSWORD,
                                       tenant_id=self._AUTH_TENANTID,
                                       auth_url='%s:5001/v2.0' % self._BASE_URL)

        if not filter(lambda network: network['tenant_id'] == tenant, neutron.list_networks()['networks']):
            network = neutron.create_network({'network':{'name':'default', 'tenant_id':tenant}})['network']
            while not neutron.list_networks(id=network['id'])['networks']:
                sleep(1)

            allocated_cidrs = map(lambda chunk: (int(chunk[0]), int(chunk[1])),
                                  map(lambda cidr: cidr['cidr'].split('/')[0].split('.')[-2:],
                                      filter(lambda subnet: subnet['cidr'].endswith('/27'),
                                             neutron.list_subnets()['subnets'])))

            if (192,0) in allocated_cidrs:
                allocated_cidrs.remove((192,0))

            if allocated_cidrs:
                max_bigchunk = max(map(lambda chunk: chunk[0], allocated_cidrs))
                max_smlchunk = max(map(lambda chunk: chunk[1], filter(lambda c: c[0] == max_bigchunk, allocated_cidrs)))

                if max_bigchunk == 191 and max_smlchunk == 224:
                    max_bigchunk = 192
                    max_smlchunk = 0

                if max_smlchunk == 224:
                    cidr = '.'.join([str(chunk) for chunk in [192, 168, max_bigchunk + 1, 0]]) + '/27'
                else:
                    cidr = '.'.join([str(chunk) for chunk in [192, 168, max_bigchunk, max_smlchunk + 32]]) + '/27'
            else:
                cidr = '192.168.0.0/27'
            subnet = neutron.create_subnet({'subnet':{'name':'default-subnet',
                                                      'cidr':cidr,
                                                      'tenant_id':tenant,
                                                      'network_id':network['id'],
                                                      'ip_version':'4'}})['subnet']
            while not neutron.list_subnets(id=subnet['id'])['subnets']:
                sleep(1)

            router = neutron.create_router({'router':{'tenant_id':tenant,
                                                      'name':'default-router'}})['router']
            while not neutron.list_routers(id=router['id'])['routers']:
                sleep(1)
            public_net_id = filter(lambda n: n['router:external'],
                                   neutron.list_networks(name='public')['networks'])[0]['id']
            neutron.add_gateway_router(router['id'], {'network_id':public_net_id})
            neutron.add_interface_router(router['id'],{'subnet_id':subnet['id']})

    def _getTenantQuota(self, tenant, tenantType):
        quota = None
        statedQuota = map(lambda q: q['FIELD_VALUE'], filter(lambda f: f['CUSTOM_FIELD_ID'] == 'PROJECT_FIELD_1',
                                                             tenant['CUSTOMFIELDS']))[0]
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

    def _enforceQuota(self, ldap_tenant, quotaDefinition, ldap_conn=None):
        openstackGroup = self._getOpenstackGroup(ldap_tenant)
        if openstackGroup:
            tenant = self._getTenantId(ldap_tenant)
            if not tenant:
                # Create or map tenant in openstack
                project = self._projectManager.list(name=ldap_tenant)
                if not project:
                    project = self._projectManager.create(ldap_tenant, self._domainManager.find(id='default'))
                self._roleManager.grant(self._roleManager.find(name='member').id,
                                        group=openstackGroup.id,
                                        project=project.id)
                tenant = project.id

            if ldap_conn and ldap_tenant in map(lambda t: t[0].split(',')[0].split('=')[1],
                                                ldap_conn.ldap_search('cn=digile.platform,ou=projects,\
                                                                       dc=forgeservicelab,dc=fi',
                                                                       SCOPE_SUBORDINATE, attrsonly=1)):
                with novaClient.Client(username=self._AUTH_USERNAME,
                                         api_key=self._AUTH_PASSWORD,
                                         tenant_id=tenant,
                                         auth_url='%s:5001/v2.0' % self._BASE_URL) as nova:
                    try:
                        nova.security_group_rules.create(nova.security_groups.find(name='default').id,
                                                         ip_protocol='tcp',
                                                         from_port=22,
                                                         to_port=22,
                                                         cidr='86.50.27.230/32')
                    except Unauthorized:
                        # butler.service not yet part of the tenant, wait for next round.
                        pass
                    except BadRequest:
                        # Rule already exists, that's OK.
                        pass

            self._ensureTenantNetwork(tenant)

            if quotaDefinition:
                service_opts = {
                    'meta': ['quota-bytes:%s' % quotaDefinition['swift_bytes']],
                    'os_username': self._AUTH_USERNAME,
                    'os_password': self._AUTH_PASSWORD,
                    'os_auth_url': '%s:5001/v2.0' % self._BASE_URL,
                    'os_storage_url': '%s:8081/v1/AUTH_digile' % self._BASE_URL,
                    'os_tenant_name': tenant
                }

                swift = switfService.SwiftService(options=service_opts)
                swift.post()

                with cinderClient.Client(username=self._AUTH_USERNAME,
                                         api_key=self._AUTH_PASSWORD,
                                         tenant_id=self._AUTH_TENANTID,
                                         auth_url=service_opts['os_auth_url']) as cinder:
                    cinder.quotas.update(tenant, gigabytes=quotaDefinition['cinder_GB'])

                with novaClient.Client(username=self._AUTH_USERNAME,
                                       api_key=self._AUTH_PASSWORD,
                                       tenant_id=self._AUTH_TENANTID,
                                       auth_url=service_opts['os_auth_url']) as nova:
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

                with neutronClient.Client(username=self._AUTH_USERNAME,
                                          password=self._AUTH_PASSWORD,
                                          tenant_id=self._AUTH_TENANTID,
                                          auth_url=service_opts['os_auth_url']) as neutron:
                    neutron.update_quota(tenant, {'quota': {'floatingip': quotaDefinition['floating_ips']}})

            with novaClient.Client(username=self._AUTH_USERNAME,
                                   api_key=self._AUTH_PASSWORD,
                                   tenant_id=self._AUTH_TENANTID,
                                   auth_url=service_opts['os_auth_url']) as nova:
                self._grantAccess(nova, 'm1.tiny', tenant)

    def enforceQuotas(self, tenantList, tenantsType, ldap_conn=None):
        """Enforce the quota for each tenant on the list.

        Args:
            tenantList (List): A list of tenants as JSON from Insightly.
            tenantsType (str): A description of the type of tenant, one of 'SDA', 'FPA' or 'FPA (CRA)'.
        """
        map(lambda t: self._enforceQuota(sanitize(t['PROJECT_NAME']), self._getTenantQuota(t, tenantsType),
                                                  ldap_conn), tenantList)
