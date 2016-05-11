# -*- coding: utf-8 -*-

from django.contrib.auth.models import User
from cabot.cabotapp.tests.tests_basic import LocalTestCase
from cabot.cabotapp.models import StatusCheck, Instance
from cabot.plugins.models import StatusCheckPluginModel
from cabot_check_graphite.plugin import GraphiteStatusCheckPlugin
from cabot.cabotapp.models import Service, StatusCheckResult
from mock import Mock, patch
import os
from .jenkins import get_job_status
import json
import time
import requests

from logging import getLogger
logger = getLogger(__name__)

def get_content(fname):
    path = os.path.join(os.path.dirname(__file__), 'fixtures/%s' % fname)
    with open(path) as f:
        return f.read()

def fake_jenkins_response(*args, **kwargs):
    resp = Mock()
    resp.json = lambda: json.loads(get_content('jenkins_response.json'))
    resp.status_code = 200
    return resp


def jenkins_blocked_response(*args, **kwargs):
    resp = Mock()
    resp.json = lambda: json.loads(get_content('jenkins_blocked_response.json'))
    resp.status_code = 200
    return resp


def throws_timeout(*args, **kwargs):
    raise requests.RequestException(u'фиктивная ошибка innit')


class TestJenkinsCheckCheckPlugin(LocalTestCase):

    def setUp(self):
        super(TestJenkinsCheckCheckPlugin, self).setUp()

        self.jenkins_check_model, created = StatusCheckPluginModel.objects.get_or_create(
	    slug='jenkins'
	    )

        self.jenkins_check = StatusCheck.objects.create(
            name='Jenkins Check',
	    check_plugin = self.jenkins_check_model,
            created_by=self.user,
            importance=Service.ERROR_STATUS,
            max_queued_build_time=10,
        )

        self.jenkins_check.save()
        self.jenkins_check = StatusCheck.objects.get(pk=self.jenkins_check.pk)
	self.service.status_checks.add(self.jenkins_check)


    @patch('cabot_check_jenkins.jenkins.requests.get', fake_jenkins_response)
    def test_jenkins_run(self):
        checkresults = self.jenkins_check.statuscheckresult_set.all()
        self.assertEqual(len(checkresults), 0)
        self.jenkins_check.run()
        checkresults = self.jenkins_check.statuscheckresult_set.all()
        self.assertEqual(len(checkresults), 1)
        self.assertFalse(self.jenkins_check.last_result().succeeded)

    @patch('cabot_check_jenkins.jenkins.requests.get', jenkins_blocked_response)
    def test_jenkins_blocked_build(self):
        checkresults = self.jenkins_check.statuscheckresult_set.all()
        self.assertEqual(len(checkresults), 0)
        self.jenkins_check.run()
        checkresults = self.jenkins_check.statuscheckresult_set.all()
        self.assertEqual(len(checkresults), 1)
        self.assertFalse(self.jenkins_check.last_result().succeeded)

    @patch('cabot_check_jenkins.plugin.requests.get', throws_timeout)
    def test_timeout_handling_in_jenkins(self):
        checkresults = self.jenkins_check.statuscheckresult_set.all()
        self.assertEqual(len(checkresults), 0)
        self.jenkins_check.run()
        checkresults = self.jenkins_check.statuscheckresult_set.all()
        self.assertEqual(len(checkresults), 1)
        self.assertTrue(self.jenkins_check.last_result().succeeded)
        self.assertIn(u'Error fetching from Jenkins - фиктивная ошибка',
                      self.jenkins_check.last_result().error)

