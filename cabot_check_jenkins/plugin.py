from django.conf import settings
from django.template import Context, Template
from django import forms
from cabot.plugins.models import StatusCheckPlugin
from cabot.plugins.forms import CheckConfigForm
from cabot.cabotapp.models import StatusCheckResult
from os import environ as env
from datetime import datetime
import logging
import requests
from django.utils import timezone


class JenkinsStatusCheckForm(forms.Form):
    max_queued_build_time = forms.IntegerField(
	help_text = 'Alert if build queued for more than this many minutes.'
    )


class JenkinsStatusCheckPlugin(StatusCheckPlugin):
    name = "Jenkins"
    slug = "jenkins"
    author = "Jonathan Balls"
    version = "0.0.1"
    font_icon = "glyphicon glyphicon-ok"

    config_form = JenkinsStatusCheckForm

    plugin_variables = [
	'JENKINS_API',
	'JENKINS_USER',
	'JENKINS_PASS' 
    ]

    def run(self, check, result):

        try:
            status = self.get_job_status(check)
            active = status['active']
            result.job_number = status['job_number']
            if status['status_code'] == 404:
                result.error = u'Job %s not found on Jenkins' % check.name
                result.succeeded = False
                return result
            elif status['status_code'] > 400:
                # Will fall through to next block
                raise Exception(u'returned %s' % status['status_code'])
        except Exception as e:
            # If something else goes wrong, we will *not* fail - otherwise
            # a lot of services seem to fail all at once.
            # Ugly to do it here but...
            result.error = u'Error fetching from Jenkins - %s' % e.message
            result.succeeded = True
            return result

        if not active:
            # We will fail if the job has been disabled
            result.error = u'Job "%s" disabled on Jenkins' % check.name
            result.succeeded = False
        else:
            if check.max_queued_build_time and status['blocked_build_time']:
                if status['blocked_build_time'] > check.max_queued_build_time * 60:
                    result.succeeded = False
                    result.error = u'Job "%s" has blocked build waiting for %ss (> %sm)' % (
                        check.name,
                        int(status['blocked_build_time']),
                        check.max_queued_build_time,
                    )
                else:
                    result.succeeded = status['succeeded']
            else:
                result.succeeded = status['succeeded']
            if not status['succeeded']:
                if result.error:
                    result.error += u'; Job "%s" failing on Jenkins' % check.name
                else:
                    result.error = u'Job "%s" failing on Jenkins' % check.name
                result.raw_data = status
        return result

    def get_job_status(self, check):
	auth = (settings.JENKINS_USER, settings.JENKINS_PASS)

	jobname = check.name
	ret = {
	    'active': True,
	    'succeeded': False,
	    'blocked_build_time': None,
	    'status_code': 200
	}
	endpoint = settings.JENKINS_API + 'job/%s/api/json' % jobname
	resp = requests.get(endpoint, auth=auth, verify=True)
	status = resp.json()
	ret['status_code'] = resp.status_code
	ret['job_number'] = status['lastBuild'].get('number', None)
	if status['color'].startswith('blue') or status['color'].startswith('green'): # Jenkins uses "blue" for successful; Hudson uses "green"
	    ret['active'] = True
	    ret['succeeded'] = True
	elif status['color'] == 'disabled':
	    ret['active'] = False
	    ret['succeeded'] = False
	if status['queueItem'] and status['queueItem']['blocked']:
	    time_blocked_since = datetime.utcfromtimestamp(
		float(status['queueItem']['inQueueSince']) / 1000).replace(tzinfo=timezone.utc)
	    ret['blocked_build_time'] = (timezone.now() - time_blocked_since).total_seconds()
	return ret

