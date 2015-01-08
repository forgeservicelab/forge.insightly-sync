"""Canned Mailer."""
import smtplib
from email.mime.text import MIMEText


class CannedMailer:

    """Send Canned Mails."""

    _FROM = 'support@forgeservicelab.fi'

    _NEW_ACCOUNT_PARTNER = {
        'subject': 'Welcome to FORGE Service Lab!',
        'body': """Welcome to FORGE Service Lab!
    Your username is {TOKEN}

    We have created an account for you which you can use to access FORGE Service Lab.
    Before accessing the services please set your password at \
    https://support.forgeservicelab.fi/password/?action=sendtoken

    In case you have requested computing capacity then please note that it takes about 10 minutes until OpenStack \
    cloud services become accessible.
    All other services are accessible immediately after you have set your password.

    You can next proceed to https://forgeservicelab.fi and click login. After that you should see black editing bar \
    with the text "Add Content". There you can fill in your organization description and offering descriptions.
    Please email or call Katariina Kalatie if you encounter any problems. Email: katariina.kalatie@digile.fi, \
    tel. +358 50 4836372.

    Best Regards,
    FORGE Service Lab Support
    support@forgeservicelab.fi"""
    }

    _NEW_ACCOUNT_DEVELOPER = {
        'subject': 'Welcome to FORGE Service Lab!',
        'body': """Welcome to FORGE Service Lab!
    Your username is {TOKEN}

    We have created an account for you which you can use to access all FORGE services.
    Before accessing the services please set your password at \
    https://support.forgeservicelab.fi/password/?action=sendtoken

    It takes about 10 minutes until OpenStack cloud service becomes accessible.
    All other services are accessible immediately after you have set your desired password.

    You can now proceed to documents in https://support.forgeservicelab.fi/

    Best Regards,

    FORGE Service Lab Support
    support@forgeservicelab.fi"""
    }

    _NEW_PROJECT = {
        'subject': 'You have new access rights',
        'body': """Welcome to FORGE Service Lab!
    You have been added as a member of the {TOKEN} project.

    This notification does not require any actions from you. You may notice new items on your FORGE services.

    Best Regards,

    FORGE Service Lab Support
    support@forgeservicelab.fi"""
    }

    _NEW_TENANT = {
        'subject': 'You have new access rights',
        'body': """Welcome to FORGE Service Lab!
    You have been added as a member of the {TOKEN} tenant.

    This notification does not require any actions from you. You may notice new projects on your OpenStack dashboard.

    Best Regards,

    FORGE Service Lab Support
    support@forgeservicelab.fi"""
    }

    _ADMIN_NOTIFICATION = {
        'subject': 'Technical Contact account created',
        'body': """Hello {TOKEN},

    We just wanted to inform you that we have now completed the FORGE Service Lab account creation for your \
    Technical contact.
    Therefore, your Technical contact is able to proceed utilizing FORGE Service Lab services.

    This notification does not require any actions from you.

    Best Regards,

    FORGE Service Lab Support
    support@forgeservicelab.fi"""
    }

    CANNED_MESSAGES = {
        'new_devel_account': _NEW_ACCOUNT_DEVELOPER,
        'new_partner_account': _NEW_ACCOUNT_PARTNER,
        'notify_admin_contact': _ADMIN_NOTIFICATION,
        'added_to_project': _NEW_PROJECT,
        'added_to_tenant': _NEW_TENANT,
    }

    def sendCannedMail(self, to, cannedMessage, token):
        """Send the specified canned mail message.

        Args:
            to (str): Email address to mail the message to.
            cannedMessage (str): Message to deliver, one of the keys on the CANNED_MESSAGES dictionary.
            token (str): String to replace the '{TOKEN}' placeholder on the canned message.
        """
        message = MIMEText(cannedMessage['body'].format(TOKEN=token))
        message['Subject'] = cannedMessage['subject']
        message['To'] = to
        message['From'] = self._FROM

        s = smtplib.SMTP('localhost')
        s.sendmail(self._FROM, to, message.as_string())
        s.quit()
