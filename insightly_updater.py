"""Update Insightly data."""
import json
from requests import get, post, put


class InsightlyUpdater:

    """Push updates to Insightly.

    Update Insightly projects based on project status changes due to LDAP synchronization operations.

    Attributes:
        INSIGHTLY_PROJECTS_URI (str): URI of Insightly's REST API Projects endpoint.
        INSIGHTLY_CATEGORIES_URI (str): URI of Insightly's REST API Categories endpoint.
        INSIGHTLY_CONTACTS_URI (str): URI of Insightly's REST API Contacts endpoint.
        INSIGHTLY_PIPELINE_STAGES_URI (str): URI of Insightly's REST API Stages endpoint.
        INSIGHTLY_PIPELINES_URI (str): URI of Insightly's REST API Pipelines endpoint.

        STATUS_RUNNING (str): Constant defining the Insightly name for a project's running status.
        STATUS_DEFERRED (str): Constant defining the Insightly name for a project's deferred status.
        STATUS_COMPLETED (str): Constant defining the Insightly name for a project's completed status.
    """

    INSIGHTLY_PROJECTS_URI = 'https://api.insight.ly/v2.1/Projects/'
    INSIGHTLY_CATEGORIES_URI = 'https://api.insight.ly/v2.1/ProjectCategories/'
    INSIGHTLY_CONTACTS_URI = 'https://api.insight.ly/v2.1/Contacts/'
    INSIGHTLY_PIPELINE_STAGES_URI = 'https://api.insight.ly/v2.1/PipelineStages/'
    INSIGHTLY_PIPELINES_URI = 'https://api.insight.ly/v2.1/Pipelines/'

    STATUS_RUNNING = 'In Progress'
    STATUS_DEFERRED = 'Deferred'
    STATUS_COMPLETED = 'Completed'

    def __init__(self, api_key=None, stages=[], tenant_category=None):
        """Initialize instance-dependent class constants.

        Args:
            api_key (str): Insightly API key.
            stages (List): A list of all the pipeline stages on the Insightly instance.
            tenant_category (str): The ID of the Insightly category that represents an OpenStack tenant project.
        """
        self.INSIGHTLY_API_KEY = api_key
        self.STAGES = stages
        self.TENANT_CATEGORY = tenant_category

    def _getInsightlyProject(self, project):
        return get(self.INSIGHTLY_PROJECTS_URI + str(project['o']), auth=(self.INSIGHTLY_API_KEY, '')).json()

    def _getNextStage(self, insightly_project):
        return filter(lambda s:
                      s['STAGE_ORDER'] in map(lambda o: o['STAGE_ORDER'] + 1,
                                              filter(lambda f: f['STAGE_ID'] == insightly_project['STAGE_ID'],
                                                     filter(lambda s:
                                                            s['PIPELINE_ID'] == insightly_project['PIPELINE_ID'],
                                                            self.STAGES))) and
                      s['PIPELINE_ID'] == insightly_project['PIPELINE_ID'], self.STAGES)[0]['STAGE_ID']

    def createDefaultTenantFor(self, project):
        """Create a default tenant for a project.

        Create a project of category 'OpenStack tenant' on Insightly if a project of type 'SDA' or 'FPA (CRA)'
        does not have at least one tenant.
        Update the parent project on Insightly so that it contains a reference to its default tenant.

        Args:
            project (dict): A project as a dictionary of relevant LDAP Attributes.

        Returns:
            str: a JSON representation of the newly created Insightly project.
        """
        parent = _getInsightlyProject(project)
        payload = {
            'PROJECT_NAME': project['cn'],
            'STATUS': self.STATUS_DEFERRED,
            'CATEGORY_ID': self.TENANT_CATEGORY,
            'CUSTOMFIELDS': parent['CUSTOMFIELDS'],
            'LINKS': [{
                'CONTACT_ID': project['owner'][0]['uid']
            }]
        }

        tenant = post(self.INSIGHTLY_PROJECTS_URI,
                      data=json.dumps(payload),
                      headers={'Content-Type': 'application/json'},
                      auth=(self.INSIGHTLY_API_KEY, '')).json()

        parent['LINKS'] = parent['LINKS'] + [{'SECOND_PROJECT_ID': tenant['PROJECT_ID']}]

        put(self.INSIGHTLY_PROJECTS_URI,
            data=json.dumps(parent),
            headers={'Content-Type': 'application/json'},
            auth=(self.INSIGHTLY_API_KEY, ''))

        return tenant

    def addUserToProject(self, userid, project):
        insightly_project = self._getInsightlyProject(map(lambda pid: dict(o=pid[1][0]),
                                                          filter(lambda attr: attr[0] == 'o', project))[0])
        insightly_project['LINKS'] += [{'CONTACT_ID': userid}]

        put(self.INSIGHTLY_PROJECTS_URI,
            data=json.dumps(insightly_project),
            headers={'Content-Type': 'application/json'},
            auth=(self.INSIGHTLY_API_KEY, ''))

    def updateProject(self, project, updateStage=True, status=None):
        """Update a project on Insightly to represent a change on its status or pipeline stage.

        Args:
            project (dict): A project as a dictionary of relevant LDAP Attributes.
            updateStage (bool, optional): Whether to update the project's pipeline to the next stage.
            status (str, optional): Modify the project status if present.
                One of STATUS_RUNNING, STATUS_DEFERRED or STATUS_COMPLETED
        """
        insightly_project = self._getInsightlyProject(project)
        if updateStage:
            insightly_project['STAGE_ID'] = self._getNextStage(insightly_project)
        if status:
            insightly_project['STATUS'] = status

        put(self.INSIGHTLY_PROJECTS_URI,
            data=json.dumps(insightly_project),
            headers={'Content-Type': 'application/json'},
            auth=(self.INSIGHTLY_API_KEY, ''))
