import re
from copy import copy, deepcopy

import pytest
import logging

from concurrent.futures.thread import ThreadPoolExecutor

from datadog_checks.base.utils.db.utils import DBMAsyncJob
from datadog_checks.sqlserver import SQLServer
from datadog_checks.sqlserver.statements import STATEMENT_METRICS_QUERY, SQL_SERVER_METRICS_COLUMNS
import xml.etree.ElementTree as ET

from .common import CHECK_NAME, CUSTOM_METRICS, CUSTOM_QUERY_A, CUSTOM_QUERY_B, EXPECTED_DEFAULT_METRICS, assert_metrics
from .utils import not_windows_ci, windows_ci
from .conftest import datadog_conn_docker


try:
    import pyodbc
except ImportError:
    pyodbc = None


@pytest.fixture(autouse=True)
def stop_orphaned_threads():
    # make sure we shut down any orphaned threads and create a new Executor for each test
    DBMAsyncJob.executor.shutdown(wait=True)
    DBMAsyncJob.executor = ThreadPoolExecutor()


# TODO: test DB version

@pytest.fixture
def dbm_instance(instance_docker):
    instance_docker['dbm'] = True
    # set the default for tests to run sychronously to ensure we don't have orphaned threads running around
    instance_docker['query_samples'] = {'enabled': True, 'run_sync': True, 'collection_interval': 1}
    # set a very small collection interval so the tests go fast
    instance_docker['query_metrics'] = {'enabled': True, 'run_sync': True, 'collection_interval': 0.1}
    return copy(instance_docker)


@not_windows_ci
@pytest.mark.integration
@pytest.mark.usefixtures('dd_environment')
@pytest.mark.parametrize(
    "database,plan_user,query,match_pattern,param_groups",
    [
        [
            "datadog_test",
            "dbo",
            "SELECT * FROM things",
            r"SELECT \* FROM things",
            (
                    (),
            ),
        ],
        [
            "datadog_test",
            "dbo",
            "SELECT * FROM things where id = ?",
            r"\(@P1 \w+\)SELECT \* FROM things where id = @P1",
            (
                    (1,),
                    (2,),
                    (3,),
            ),
        ],
        [
            "master",
            None,
            "SELECT * FROM datadog_test.dbo.things where id = ?",
            r"\(@P1 \w+\)SELECT \* FROM datadog_test.dbo.things where id = @P1",
            (
                    (1,),
                    (2,),
                    (3,),
            ),
        ],
        [
            "datadog_test",
            "dbo",
            "SELECT * FROM things where id = ? and name = ?",
            r"\(@P1 \w+,@P2 NVARCHAR\(\d+\)\)SELECT \* FROM things where id = @P1 and name = @P2",
            (
                    (1, "hello"),
                    (2, "there"),
                    (3, "bill"),
            ),
        ],
    ],
)
def test_statement_metrics_and_plans(aggregator, dd_run_check, dbm_instance, bob_conn, database, plan_user, query,
                                     param_groups, match_pattern):
    check = SQLServer(CHECK_NAME, {}, [dbm_instance])

    with bob_conn.cursor() as cursor:
        cursor.execute("USE {}".format(database))

    def _run_test_queries():
        with bob_conn.cursor() as cursor:
            for params in param_groups:
                cursor.execute(query, params)

    _run_test_queries()
    dd_run_check(check)
    aggregator.reset()
    _run_test_queries()
    dd_run_check(check)

    expected_instance_tags = set(dbm_instance.get('tags', []))
    expected_instance_tags_with_db = set(dbm_instance.get('tags', [])) | {
        "db:{}".format(database)
    }

    # dbm-metrics
    dbm_metrics = aggregator.get_event_platform_events("dbm-metrics")
    assert len(dbm_metrics) == 1, "should have collected exactly one dbm-metrics payload"
    payload = dbm_metrics[0]
    # host metadata
    assert payload['sqlserver_version'].startswith("Microsoft SQL Server"), "invalid version"
    assert payload['host'] == "stubbed.hostname", "wrong hostname"
    assert set(payload['tags']) == expected_instance_tags, "wrong instance tags for dbm-metrics event"
    assert type(payload['min_collection_interval']) in (float, int), "invalid min_collection_interval"
    # metrics rows
    sqlserver_rows = payload.get('sqlserver_rows', [])
    assert sqlserver_rows, "should have collected some sqlserver query metrics rows"
    matching_rows = [r for r in sqlserver_rows if re.match(match_pattern, r['text'], re.IGNORECASE)]
    assert len(matching_rows) >= 1, "expected at least one matching metrics row"
    total_execution_count = sum([r['execution_count'] for r in matching_rows])
    assert total_execution_count == len(param_groups), "wrong execution count"
    for row in matching_rows:
        assert row['query_signature'], "missing query signature"
        assert row['database_name'] == database, "incorrect database_name"
        assert row['user_name'] == plan_user, "incorrect user_name"
        for column in SQL_SERVER_METRICS_COLUMNS:
            assert column in row, "missing required metrics column {}".format(column)
            assert type(row[column]) in (float, int), "wrong type for metrics column {}".format(column)

    dbm_samples = aggregator.get_event_platform_events("dbm-samples")
    assert dbm_samples, "should have collected at least one sample"

    matching_samples = [s for s in dbm_samples if re.match(match_pattern, s['db']['statement'], re.IGNORECASE)]
    assert matching_samples, "should have collected some matching samples"

    # validate common host fields
    for event in matching_samples:
        assert event['host'] == "stubbed.hostname", "wrong hostname"
        assert event['ddsource'] == "sqlserver", "wrong source"
        assert event['ddagentversion'], "missing ddagentversion"
        assert set(event['ddtags'].split(',')) == expected_instance_tags_with_db, "wrong instance tags for plan event"

    plan_events = [s for s in dbm_samples if s['dbm_type'] == "plan"]
    assert plan_events, "should have collected some plans"

    for event in plan_events:
        assert event['db']['plan']['definition'], "event plan definition missing"
        parsed_plan = ET.fromstring(event['db']['plan']['definition'])
        assert parsed_plan.tag.endswith("ShowPlanXML"), "plan does not match expected structure"

    fqt_events = [s for s in dbm_samples if s['dbm_type'] == "fqt"]
    assert fqt_events, "should have collected some FQT events"



@not_windows_ci
@pytest.mark.integration
@pytest.mark.usefixtures('dd_environment')
def test_statement_basic_metrics_query(datadog_conn_docker):
    test_query = "select * from sys.databases"

    # run this test query to guarantee there's at least one application query in the query plan cache
    with datadog_conn_docker.cursor() as cursor:
        cursor.execute(test_query)
        cursor.fetchall()

    # this test ensures that we're able to run the basic STATEMENT_METRICS_QUERY without error
    # the dm_exec_plan_attributes table-valued function used in this query contains a "sql_variant" data type
    # which is not supported by pyodbc, so we need to explicitly cast the field into the type we expect to see
    # without the cast this is expected to fail with
    # pyodbc.ProgrammingError: ('ODBC SQL type -150 is not yet supported.  column-index=77  type=-150', 'HY106')
    with datadog_conn_docker.cursor() as cursor:
        logging.debug("running statement_metrics_query: %s", STATEMENT_METRICS_QUERY)
        cursor.execute(STATEMENT_METRICS_QUERY)

        columns = [i[0] for i in cursor.description]
        # construct row dicts manually as there's no DictCursor for pyodbc
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        matching = [r for r in rows if r['text'] == test_query]
        assert matching, "the test query should be visible in the query stats"
        row = matching[0]

        cursor.execute(
            "select count(*) from sys.dm_exec_query_stats where query_hash = ? and query_plan_hash = ?",
            row['query_hash'],
            row['query_plan_hash']
        )

        assert cursor.fetchall()[0][0] >= 1, "failed to read back the same query stats using the query and plan hash"
