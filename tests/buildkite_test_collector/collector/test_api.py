from uuid import uuid4

import os
import mock
import responses
import pytest
import sys

from buildkite_test_collector.collector.run_env import RunEnvBuilder
from buildkite_test_collector.collector.api import API
from buildkite_test_collector.collector.payload import Payload
from requests.exceptions import ReadTimeout, ConnectTimeout


def test_submit_with_missing_api_key_environment_variable_returns_none():
    env = {"CI": "true", "BUILDKITE_ANALYTICS_TOKEN": None}
    payload = Payload.init(RunEnvBuilder(env).build())

    api = API(env)
    assert next(api.submit(payload)) is None


def test_submit_with_invalid_api_key_environment_variable_returns_none():
    env = {"CI": "true", "BUILDKITE_ANALYTICS_TOKEN": "\n"}
    payload = Payload.init(RunEnvBuilder(env).build())

    api = API(env)
    assert next(api.submit(payload)) is None

@responses.activate
@pytest.mark.skipif(sys.version_info < (3, 9), reason="requires python3.9 or higher")
def test_submit_with_payload_timeout_captures_ConnectTimeout_error(capfd, successful_test):
    responses.add(
        responses.POST,
        "https://analytics-api.buildkite.com/v1/uploads",
        body=ConnectTimeout("Error"))

    env = {"CI": "true", "BUILDKITE_ANALYTICS_TOKEN": str(uuid4())}
    payload = Payload.init(RunEnvBuilder(env).build())
    payload = Payload.started(payload)

    payload = payload.push_test_data(successful_test)

    api = API(env)
    result = next(api.submit(payload))
    captured = capfd.readouterr()

    assert captured.err.startswith("buildkite-test-collector - WARNING -")
    assert "ConnectTimeout" in captured.err

@responses.activate
@pytest.mark.skipif(sys.version_info < (3, 9), reason="requires python3.9 or higher")
def test_submit_with_payload_timeout_captures_ReadTimeout_error(capfd, successful_test):
    responses.add(
        responses.POST,
        "https://analytics-api.buildkite.com/v1/uploads",
        body=ReadTimeout("Error"))

    env = {"CI": "true", "BUILDKITE_ANALYTICS_TOKEN": str(uuid4())}
    payload = Payload.init(RunEnvBuilder(env).build())
    payload = Payload.started(payload)

    payload = payload.push_test_data(successful_test)

    api = API(env)
    result = next(api.submit(payload))
    captured = capfd.readouterr()

    assert captured.err.startswith("buildkite-test-collector - WARNING -")
    assert "ReadTimeout" in captured.err

@responses.activate
def test_submit_with_payload_returns_an_api_response(successful_test):
    responses.add(
        responses.POST,
        "https://analytics-api.buildkite.com/v1/uploads",
        json={'id': str(uuid4()),
              'run_id': str(uuid4()),
              'queued': 1,
              'skipped': 0,
              'errors': [],
              'run_url': 'https://buildkite.com/organizations/alembic/analytics/suites/test/runs/52c5d9f6-a4f2-4a2d-a1e6-993335789c92'},
        status=202)

    env = {"CI": "true", "BUILDKITE_ANALYTICS_TOKEN": str(uuid4())}
    payload = Payload.init(RunEnvBuilder(env).build())
    payload = Payload.started(payload)

    payload = payload.push_test_data(successful_test)

    api = API(env)
    result = next(api.submit(payload))
    assert result

    assert result.status_code >= 200
    assert result.status_code < 300

    json = result.json()
    assert len(json["errors"]) == 0
    assert json['queued'] == 1

@responses.activate
def test_submit_with_bad_response(successful_test):
    responses.add(
        responses.POST,
        "https://analytics-api.buildkite.com/v1/uploads",
        json={'error': str(uuid4())},
        status=401)

    env = {"CI": "true", "BUILDKITE_ANALYTICS_TOKEN": str(uuid4())}
    payload = Payload.init(RunEnvBuilder(env).build())
    payload = Payload.started(payload)

    payload = payload.push_test_data(successful_test)

    api = API(env)
    result = next(api.submit(payload))

    assert result is None

@responses.activate
def test_submit_with_large_payload_batches_requests(successful_test, failed_test):
    responses.add(
        responses.POST,
        "https://analytics-api.buildkite.com/v1/uploads",
        json={'id': str(uuid4()),
              'run_id': str(uuid4()),
              'queued': 1,
              'skipped': 0,
              'errors': [],
              'run_url': 'https://buildkite.com/organizations/alembic/analytics/suites/test/runs/52c5d9f6-a4f2-4a2d-a1e6-993335789c92'},
        status=202)
    responses.add(
        responses.POST,
        "https://analytics-api.buildkite.com/v1/uploads",
        json={'id': str(uuid4()),
              'run_id': str(uuid4()),
              'queued': 1,
              'skipped': 0,
              'errors': [],
              'run_url': 'https://buildkite.com/organizations/alembic/analytics/suites/test/runs/52c5d9f6-a4f2-4a2d-a1e6-993335789c92'},
        status=202)

    env = {"CI": "true", "BUILDKITE_ANALYTICS_TOKEN": str(uuid4())}
    payload = Payload.init(RunEnvBuilder(env).build())
    payload = Payload.started(payload)

    payload = payload.push_test_data(successful_test)
    payload = payload.push_test_data(failed_test)

    api = API(env)
    results = [response for response in api.submit(payload, batch_size=1)]
    assert len(results) == 2

    for result in results:
        assert result
        assert result.status_code >= 200
        assert result.status_code < 300

        json = result.json()
        assert len(json["errors"]) == 0
        assert json['queued'] == 1

@responses.activate
def test_submit_with_batches_and_errors(capfd, successful_test, failed_test):
    responses.add(
        responses.POST,
        "https://analytics-api.buildkite.com/v1/uploads",
        body=ConnectTimeout("Error"))
    responses.add(
        responses.POST,
        "https://analytics-api.buildkite.com/v1/uploads",
        json={'id': str(uuid4()),
              'run_id': str(uuid4()),
              'queued': 1,
              'skipped': 0,
              'errors': [],
              'run_url': 'https://buildkite.com/organizations/alembic/analytics/suites/test/runs/52c5d9f6-a4f2-4a2d-a1e6-993335789c92'},
        status=202)

    env = {"CI": "true", "BUILDKITE_ANALYTICS_TOKEN": str(uuid4())}
    payload = Payload.init(RunEnvBuilder(env).build())
    payload = Payload.started(payload)

    payload = payload.push_test_data(successful_test)
    payload = payload.push_test_data(failed_test)

    api = API(env)
    results = [response for response in api.submit(payload, batch_size=1)]
    assert len(results) == 2

    assert not results[0]
    captured = capfd.readouterr()
    assert captured.err.startswith("buildkite-test-collector - WARNING -")
    assert "ConnectTimeout" in captured.err

    result = results[1]
    assert result
    assert result.status_code >= 200
    assert result.status_code < 300

    json = result.json()
    assert len(json["errors"]) == 0
    assert json['queued'] == 1

@responses.activate
def test_api_url_override(successful_test):
    upload_id = str(uuid4())

    responses.add(
        responses.POST,
        "http://something-else.example.com/v1/uploads",
        json={'upload_id': upload_id},
        status=202)

    env = {
        "BUILDKITE_ANALYTICS_API_URL": "http://something-else.example.com/v1",
        "CI": "true",
        "BUILDKITE_ANALYTICS_TOKEN": str(uuid4()),
    }

    payload = Payload.init(RunEnvBuilder(env).build())
    payload = Payload.started(payload)

    payload = payload.push_test_data(successful_test)

    api = API(env)
    result = next(api.submit(payload))
    assert result

    assert result.status_code >= 200
    assert result.status_code < 300

    json = result.json()
    assert json['upload_id'] == upload_id
