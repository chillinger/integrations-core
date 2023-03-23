import json
import logging
import os

import mock
import pytest
from requests.exceptions import HTTPError

from datadog_checks.dev import get_here
from datadog_checks.dev.http import MockResponse
from datadog_checks.openstack_controller.api.api_rest import ApiRest
from datadog_checks.openstack_controller.api.api_sdk import ApiSdk
from datadog_checks.openstack_controller.api.factory import make_api
from datadog_checks.openstack_controller.config import OpenstackConfig

from .common import TEST_OPENSTACK_CONFIG_PATH

pytestmark = [pytest.mark.unit]


def test_make_api_rest():
    instance = {
        'keystone_server_url': 'http://10.164.0.83/identity',
        'user_name': 'admin',
        'user_password': 'password',
    }
    config = OpenstackConfig(mock.MagicMock(), instance)
    api = make_api(config, mock.MagicMock(), mock.MagicMock())
    assert isinstance(api, ApiRest)


def test_make_api_sdk():
    instance = {
        'openstack_cloud_name': 'test_cloud',
        'openstack_config_file_path': TEST_OPENSTACK_CONFIG_PATH,
    }
    config = OpenstackConfig(mock.MagicMock(), instance)
    api = make_api(config, mock.MagicMock(), mock.MagicMock())
    assert isinstance(api, ApiSdk)


def test_rest_create_connection_exception():
    with pytest.raises(HTTPError):
        mocked_http = mock.MagicMock()
        mocked_http.get.side_effect = [HTTPError()]
        instance = {
            'keystone_server_url': 'http://10.164.0.83/identity',
            'user_name': 'admin',
            'user_password': 'password',
        }
        config = OpenstackConfig(mock.MagicMock(), instance)
        api = make_api(config, logging, mocked_http)
        api.create_connection()
    assert mocked_http.get.call_count == 1


def test_rest_create_connection_http_error_500():
    with pytest.raises(HTTPError):
        mocked_http = mock.MagicMock()
        mocked_http.get.side_effect = [MockResponse(status_code=500)]
        instance = {
            'keystone_server_url': 'http://10.164.0.83/identity',
            'user_name': 'admin',
            'user_password': 'password',
        }
        config = OpenstackConfig(mock.MagicMock(), instance)
        api = make_api(config, logging, mocked_http)
        api.create_connection()
    assert mocked_http.get.call_count == 1


def test_rest_create_connection_ok():
    mocked_http = mock.MagicMock()
    mocked_http.get.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/get.json'),
            status_code=200,
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/projects/get.json'),
            status_code=200,
        ),
    ]
    mocked_http.post.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'test1234'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_1'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_2'},
        ),
    ]
    instance = {
        'keystone_server_url': 'http://10.164.0.83/identity',
        'user_name': 'admin',
        'user_password': 'password',
    }
    config = OpenstackConfig(mock.MagicMock(), instance)
    api = make_api(config, logging, mocked_http)
    api.create_connection()
    assert mocked_http.get.call_count == 2
    mocked_http.get.assert_has_calls(
        [mock.call('http://10.164.0.83/identity/v3'), mock.call('http://10.164.0.83/identity/v3/auth/projects')]
    )
    assert mocked_http.post.call_count == 3
    mocked_http.post.assert_has_calls(
        [
            mock.call(
                'http://10.164.0.83/identity/v3/auth/tokens',
                data='{"auth": {"identity": {"methods": ["password"], '
                '"password": {"user": {"name": "admin", "password": "password", "domain": {"id": "default"}}}}}}',
            ),
            mock.call(
                'http://10.164.0.83/identity/v3/auth/tokens',
                data='{"auth": {"identity": {"methods": ["password"], '
                '"password": {"user": {"name": "admin", "password": "password", "domain": {"id": "default"}}}}, '
                '"scope": {"project": {"id": "667aee39f2b64032b4d7585809d31e6f"}}}}',
            ),
            mock.call(
                'http://10.164.0.83/identity/v3/auth/tokens',
                data='{"auth": {"identity": {"methods": ["password"], '
                '"password": {"user": {"name": "admin", "password": "password", "domain": {"id": "default"}}}}, '
                '"scope": {"project": {"id": "c165a94e230a4390af02d7394fb1fa69"}}}}',
            ),
        ]
    )


def test_rest_get_projects():
    mocked_http = mock.MagicMock()
    mocked_http.get.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/get.json'),
            status_code=200,
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/projects/get.json'),
            status_code=200,
        ),
    ]
    mocked_http.post.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'test1234'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_1'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_2'},
        ),
    ]
    instance = {
        'keystone_server_url': 'http://10.164.0.83/identity',
        'user_name': 'admin',
        'user_password': 'password',
    }
    config = OpenstackConfig(mock.MagicMock(), instance)
    api = make_api(config, logging, mocked_http)
    api.create_connection()
    projects = api.get_projects()
    assert projects == [
        {'id': '667aee39f2b64032b4d7585809d31e6f', 'name': 'admin'},
        {'id': 'c165a94e230a4390af02d7394fb1fa69', 'name': 'demo'},
    ]


def test_rest_get_compute_response_time():
    total_seconds = 0.0015
    mocked_total_seconds = mock.MagicMock(return_value=total_seconds)
    mocked_elapsed = mock.MagicMock()
    mocked_elapsed.total_seconds = mocked_total_seconds
    mocked_compute_response_time = MockResponse(
        file_path=os.path.join(get_here(), 'fixtures/http/nova/microversion_none/compute/v2.1/get.json'),
        status_code=200,
    )
    mocked_compute_response_time.elapsed = mocked_elapsed
    mocked_http = mock.MagicMock()
    mocked_http.get.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/get.json'),
            status_code=200,
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/projects/get.json'),
            status_code=200,
        ),
        mocked_compute_response_time,
    ]
    mocked_http.post.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'test1234'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_1'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_2'},
        ),
    ]
    instance = {
        'keystone_server_url': 'http://10.164.0.83/identity',
        'user_name': 'admin',
        'user_password': 'password',
    }
    config = OpenstackConfig(mock.MagicMock(), instance)
    api = make_api(config, logging, mocked_http)
    api.create_connection()
    compute_response_time = api.get_compute_response_time("667aee39f2b64032b4d7585809d31e6f")
    mocked_http.get.assert_has_calls([mock.call('http://127.0.0.1:8774/compute/v2.1')])
    assert compute_response_time == total_seconds * 1000


def test_rest_get_compute_limits():
    mocked_http = mock.MagicMock()
    mocked_http.get.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/get.json'),
            status_code=200,
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/projects/get.json'),
            status_code=200,
        ),
        MockResponse(
            file_path=os.path.join(
                get_here(),
                'fixtures/http/nova/microversion_none/compute/v2.1/limits/667aee39f2b64032b4d7585809d31e6f.json'
            ),
            status_code=200,
        ),
    ]
    mocked_http.post.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'test1234'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_1'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_2'},
        ),
    ]
    instance = {
        'keystone_server_url': 'http://10.164.0.83/identity',
        'user_name': 'admin',
        'user_password': 'password',
    }
    config = OpenstackConfig(mock.MagicMock(), instance)
    api = make_api(config, logging, mocked_http)
    api.create_connection()
    compute_limits = api.get_compute_limits("667aee39f2b64032b4d7585809d31e6f")
    mocked_http.get.assert_has_calls(
        [mock.call('http://127.0.0.1:8774/compute/v2.1/limits?tenant_id=667aee39f2b64032b4d7585809d31e6f')]
    )
    with open(os.path.join(get_here(), 'fixtures/api/compute/nova_microversion_none/limits.json'), 'r') as limits:
        assert compute_limits == json.load(limits)


def test_rest_get_compute_limits_nova_microversion_latest():
    mocked_http = mock.MagicMock()
    mocked_http.get.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/get.json'),
            status_code=200,
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/projects/get.json'),
            status_code=200,
        ),
        MockResponse(
            file_path=os.path.join(
                get_here(),
                'fixtures/http/nova/microversion_latest/compute/v2.1/limits/667aee39f2b64032b4d7585809d31e6f.json'
            ),
            status_code=200,
        ),
    ]
    mocked_http.post.side_effect = [
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'test1234'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_1'},
        ),
        MockResponse(
            file_path=os.path.join(get_here(), 'fixtures/http/keystone/identity/v3/auth/tokens/post.json'),
            status_code=200,
            headers={'X-Subject-Token': 'project_2'},
        ),
    ]
    instance = {
        'keystone_server_url': 'http://10.164.0.83/identity',
        'user_name': 'admin',
        'user_password': 'password',
        'nova_microversion': 'latest'
    }
    config = OpenstackConfig(mock.MagicMock(), instance)
    api = make_api(config, logging, mocked_http)
    api.create_connection()
    compute_limits = api.get_compute_limits("667aee39f2b64032b4d7585809d31e6f")
    mocked_http.get.assert_has_calls(
        [mock.call('http://127.0.0.1:8774/compute/v2.1/limits?tenant_id=667aee39f2b64032b4d7585809d31e6f')]
    )
    with open(os.path.join(get_here(), 'fixtures/api/compute/nova_microversion_latest/limits.json'), 'r') as limits:
        assert compute_limits == json.load(limits)