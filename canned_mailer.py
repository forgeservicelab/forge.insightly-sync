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

We have created a user account for you which you can use to access FORGE Service Lab.
Before accessing the services please set your password at \
https://support.forgeservicelab.fi/password/?action=sendtoken

In case you have computing resource allocation then please note that it takes about 10 minutes until \
cloud services become accessible. \
All other services are accessible immediately after you have set your desired password.

You can proceed to https://forgeservicelab.fi and click login after you have set the password. \
Then you should see black editing bar with the text "Add Content". \
There you can fill in your organization description and offering descriptions.

Should you have any questions then please contact Katariina Kalatie. Email: katariina.kalatie@digile.fi, \
tel. +358 50 4836372.


Best Regards,
FORGE Service Lab Support
support@forgeservicelab.fi"""
    }

    _NEW_ACCOUNT_DEVELOPER = {
        'subject': 'Welcome to FORGE Service Lab!',
        'body': """Welcome to FORGE Service Lab!
Your username is {TOKEN}

We have created a user account for you which you can use to access all FORGE Service Lab services.
Before accessing the services please set your password at \
https://support.forgeservicelab.fi/password/?action=sendtoken

It takes about 10 minutes until the cloud service becomes accessible.
All other services are accessible immediately after you have set your desired password.

You can proceed to documents in https://support.forgeservicelab.fi/ after you have set the password.\
If you're project's Technical Contact then you might want to start by adding new members to the project.


Best Regards,

FORGE Service Lab Support
support@forgeservicelab.fi"""
    }

    _NEW_PROJECT = {
        'subject': 'You have new access rights in FORGE Service Lab',
        'body': """
You have been added as a member to {TOKEN} project in FORGE Service Lab by your project's Technical Contact.
You may notice new features when using FORGE Service Lab services.

This notification does not require any actions from you.


Best Regards,

FORGE Service Lab Support
support@forgeservicelab.fi"""
    }

    _NEW_TENANT = {
        'subject': 'You have new access rights in FORGE Service Lab cloud service',
        'body': """
You have been added as a member to {TOKEN} project in FORGE Service Lab cloud service.
You may notice new features when using FORGE Service Lab's cloud service dashboard.

This notification does not require any actions from you.


Best Regards,

FORGE Service Lab Support
support@forgeservicelab.fi"""
    }

    _ADMIN_NOTIFICATION = {
        'subject': 'Your project in FORGE Service Lab is ready to start!',
        'body': """Hello {TOKEN},

We just wanted to inform you that we have completed setting up a project and a user account for your \
Technical Contact in FORGE Service Lab.
Therefore, your project's Technical Contact is able to proceed utilizing FORGE Service Lab services.

This notification does not require any actions from you.


Best Regards,

FORGE Service Lab Support
support@forgeservicelab.fi"""
    }

    _DEL_FROM_PROJECT = {
        'subject': 'Your access to FORGE Service Lab was modified!',
        'body': """
Your user account was removed from the {TOKEN} project in FORGE Service Lab by the project's Technical Contact.

This notification does not require any actions from you. 


Best Regards,

FORGE Service Lab Support
support@forgeservicelab.fi"""
    }

    _DEL_FROM_TENANT = {
        'subject': 'Your access to the FORGE Service Lab cloud service was modified!',
        'body': """
Your user account was removed from the OpenStack project {TOKEN} by the project's Technical Contact.

This notification does not require any actions from you.


Best Regards,

FORGE Service Lab Support
support@forgeservicelab.fi"""
    }

    _DISABLE_ACCOUNT_DEVELOPER = {
        'subject': 'Your user account in FORGE Service Lab was disabled!',
        'body': """
Your user account {TOKEN} in FORGE Service Lab was disabled by your project's technical contact person.

This notification does not require any actions from you.


Best Regards,

FORGE Service Lab Support
support@forgeservicelab.fi"""
    }

    _DISABLE_ACCOUNT_PARTNER = {
        'subject': 'Your user account in FORGE Service Lab was disabled!',
        'body': """
Your user account {TOKEN} in FORGE Service Lab was disabled.

A typical reason for disabling the user account is the contract expiration and this notification does \
not require any actions from you.

Should you have any questions then please contact Katariina Kalatie. Email: katariina.kalatie@digile.fi, \
tel. +358 50 4836372.


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
        'deleted_from_project': _DEL_FROM_PROJECT,
        'deleted_from_tenant': _DEL_FROM_TENANT,
        'disabled_devel_account': _DISABLE_ACCOUNT_DEVELOPER,
        'disabled_partner_account': _DISABLE_ACCOUNT_PARTNER,
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
