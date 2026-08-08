"""
SQL Server 连接与执行的用例，驱动层用 mock 替换。

重点覆盖两类容易照抄 MySQL 路径写错的地方：
  - charset 字段是 MySQL 概念，默认值 utf8mb4 不是合法 FreeTDS 字符集
  - pymssql 对 SELECT 的 cursor.rowcount 常返回 -1，不能拿来当结果行数
"""
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from . import db_executor, mssql_executor
from .models import DataSource


def build_datasource(**overrides):
    defaults = {
        'name': 'prod-mssql',
        'db_type': 'sqlserver',
        'host': '10.0.0.9',
        'port': 1433,
        'user': 'auditor',
        'password': 'secret',
        'charset': 'utf8mb4',
    }
    defaults.update(overrides)
    return DataSource(**defaults)


def build_connection(rows=None, description=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchall.return_value = rows or []
    cursor.fetchmany.return_value = rows or []
    cursor.description = description
    cursor.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


class ConnectTests(SimpleTestCase):
    @patch('sqlaudit.mssql_executor.pymssql')
    def test_charset_field_is_ignored(self, mock_pymssql):
        # utf8mb4 是 MySQL 的字符集名，原样传给 FreeTDS 会直接连不上
        mssql_executor._connect(build_datasource(charset='utf8mb4'))
        kwargs = mock_pymssql.connect.call_args.kwargs
        self.assertEqual(kwargs['charset'], 'UTF-8')

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_port_is_coerced_to_int(self, mock_pymssql):
        mssql_executor._connect(build_datasource(port='1433'))
        self.assertEqual(mock_pymssql.connect.call_args.kwargs['port'], 1433)

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_database_omitted_when_not_given(self, mock_pymssql):
        mssql_executor._connect(build_datasource())
        self.assertNotIn('database', mock_pymssql.connect.call_args.kwargs)

    @patch('sqlaudit.mssql_executor.pymssql', None)
    def test_missing_driver_raises(self):
        with self.assertRaises(RuntimeError):
            mssql_executor._connect(build_datasource())


class TestConnectionTests(SimpleTestCase):
    @patch('sqlaudit.mssql_executor.pymssql')
    def test_success(self, mock_pymssql):
        mock_pymssql.connect.return_value = MagicMock()
        self.assertEqual(mssql_executor.test_connection(build_datasource()), (True, '连接成功'))

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_failure_returns_message(self, mock_pymssql):
        mock_pymssql.connect.side_effect = Exception('login failed')
        success, message = mssql_executor.test_connection(build_datasource())
        self.assertFalse(success)
        self.assertIn('login failed', message)


class ListDatabasesTests(SimpleTestCase):
    @patch('sqlaudit.mssql_executor.pymssql')
    def test_filters_system_databases(self, mock_pymssql):
        conn, cursor = build_connection(rows=[
            ('master',), ('tempdb',), ('model',), ('msdb',), ('billing',), ('settlement',),
        ])
        mock_pymssql.connect.return_value = conn

        self.assertEqual(
            mssql_executor.list_databases(build_datasource()),
            ['billing', 'settlement'],
        )
        self.assertIn('state = 0', cursor.execute.call_args.args[0])

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_returns_empty_on_error(self, mock_pymssql):
        mock_pymssql.connect.side_effect = Exception('boom')
        self.assertEqual(mssql_executor.list_databases(build_datasource()), [])


class ListSchemasTests(SimpleTestCase):
    @patch('sqlaudit.mssql_executor.pymssql')
    def test_filters_system_schemas(self, mock_pymssql):
        conn, _ = build_connection(rows=[
            ('sys',), ('INFORMATION_SCHEMA',), ('db_owner',), ('guest',), ('dbo',), ('report',),
        ])
        mock_pymssql.connect.return_value = conn

        self.assertEqual(
            mssql_executor.list_schemas(build_datasource(), 'billing'),
            ['dbo', 'report'],
        )

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_falls_back_to_dbo_when_only_system_schemas(self, mock_pymssql):
        conn, _ = build_connection(rows=[('sys',), ('db_owner',)])
        mock_pymssql.connect.return_value = conn
        self.assertEqual(mssql_executor.list_schemas(build_datasource(), 'billing'), ['dbo'])

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_returns_empty_on_error(self, mock_pymssql):
        mock_pymssql.connect.side_effect = Exception('boom')
        self.assertEqual(mssql_executor.list_schemas(build_datasource(), 'billing'), [])


class ExecuteReadTests(SimpleTestCase):
    @patch('sqlaudit.mssql_executor.pymssql')
    def test_row_count_uses_len_not_rowcount(self, mock_pymssql):
        # pymssql 对 SELECT 常返回 rowcount = -1，照抄 MySQL 路径会把行数报成 -1
        conn, _ = build_connection(
            rows=[{'id': 1}, {'id': 2}],
            description=[('id',)],
            rowcount=-1,
        )
        mock_pymssql.connect.return_value = conn

        success, columns, rows, count, duration, error = mssql_executor.execute_read(
            build_datasource(), 'billing', 'SELECT id FROM t',
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(count, 2)
        self.assertEqual(columns, ['id'])
        self.assertEqual(len(rows), 2)

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_empty_description_yields_no_columns(self, mock_pymssql):
        conn, _ = build_connection(rows=[], description=None)
        mock_pymssql.connect.return_value = conn
        success, columns, rows, count, _duration, error = mssql_executor.execute_read(
            build_datasource(), 'billing', 'SELECT 1 WHERE 1 = 0',
        )
        self.assertTrue(success)
        self.assertEqual((columns, rows, count, error), ([], [], 0, None))

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_failure_returns_error_text(self, mock_pymssql):
        conn, cursor = build_connection()
        cursor.execute.side_effect = Exception('invalid object name')
        mock_pymssql.connect.return_value = conn

        success, _columns, _rows, _count, _duration, error = mssql_executor.execute_read(
            build_datasource(), 'billing', 'SELECT * FROM nope',
        )
        self.assertFalse(success)
        self.assertIn('invalid object name', error)


class ExecuteWriteTests(SimpleTestCase):
    @patch('sqlaudit.mssql_executor.pymssql')
    def test_commits_and_accumulates_affected_rows(self, mock_pymssql):
        conn, cursor = build_connection(rowcount=3)
        mock_pymssql.connect.return_value = conn

        success, affected, _duration, log = mssql_executor.execute_write(
            build_datasource(), 'billing', 'UPDATE a SET x = 1; UPDATE b SET y = 2;',
        )

        self.assertTrue(success)
        self.assertEqual(affected, 6)
        self.assertEqual(cursor.execute.call_count, 2)
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        self.assertIn('语句 #2', log)

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_rolls_back_on_failure(self, mock_pymssql):
        conn, cursor = build_connection(rowcount=1)
        cursor.execute.side_effect = [None, Exception('constraint violation')]
        mock_pymssql.connect.return_value = conn

        success, affected, _duration, log = mssql_executor.execute_write(
            build_datasource(), 'billing', 'UPDATE a SET x = 1; UPDATE b SET y = 2;',
        )

        self.assertFalse(success)
        self.assertEqual(affected, 0)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        self.assertIn('constraint violation', log)

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_procedure_body_is_sent_as_one_statement(self, mock_pymssql):
        # 过程体里的分号不该被切开，否则发到服务端的是碎片
        conn, cursor = build_connection(rowcount=0)
        mock_pymssql.connect.return_value = conn
        script = 'CREATE PROCEDURE p AS\nBEGIN\n    SELECT 1;\n    SELECT 2;\nEND'

        mssql_executor.execute_write(build_datasource(), 'billing', script)

        self.assertEqual(cursor.execute.call_count, 1)

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_schema_is_recorded_in_log(self, mock_pymssql):
        conn, _ = build_connection(rowcount=1)
        mock_pymssql.connect.return_value = conn
        _success, _affected, _duration, log = mssql_executor.execute_write(
            build_datasource(), 'billing', 'UPDATE a SET x = 1;', schema='report',
        )
        self.assertIn('report', log)

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_empty_content_is_rejected_before_connecting(self, mock_pymssql):
        success, _affected, _duration, log = mssql_executor.execute_write(
            build_datasource(), 'billing', '   ',
        )
        self.assertFalse(success)
        self.assertIn('为空', log)
        mock_pymssql.connect.assert_not_called()

    @patch('sqlaudit.mssql_executor.pymssql')
    def test_connection_failure_is_reported(self, mock_pymssql):
        mock_pymssql.connect.side_effect = Exception('network unreachable')
        success, _affected, _duration, log = mssql_executor.execute_write(
            build_datasource(), 'billing', 'UPDATE a SET x = 1;',
        )
        self.assertFalse(success)
        self.assertIn('连接失败', log)


class DbExecutorDispatchTests(SimpleTestCase):
    @patch('sqlaudit.db_executor.mssql_executor.test_connection', return_value=(True, '连接成功'))
    def test_test_connection_routes_to_mssql(self, mock_test):
        db_executor.test_connection(build_datasource())
        mock_test.assert_called_once()

    @patch('sqlaudit.db_executor.mssql_executor.list_databases', return_value=['billing'])
    def test_get_databases_routes_to_mssql(self, mock_list):
        self.assertEqual(db_executor.get_databases(build_datasource()), ['billing'])
        mock_list.assert_called_once()

    @patch('sqlaudit.db_executor.mssql_executor.list_schemas', return_value=['dbo'])
    def test_get_schemas_routes_to_mssql(self, mock_list):
        self.assertEqual(db_executor.get_schemas(build_datasource(), 'billing'), ['dbo'])
        mock_list.assert_called_once()

    def test_get_schemas_is_empty_for_other_types(self):
        self.assertEqual(db_executor.get_schemas(DataSource(db_type='mysql'), 'app'), [])
        self.assertEqual(db_executor.get_schemas(DataSource(db_type='mongodb'), 'app'), [])

    @patch('sqlaudit.db_executor.mssql_executor.execute_write', return_value=(True, 1, 5, 'ok'))
    def test_execute_sql_passes_schema(self, mock_write):
        db_executor.execute_sql(build_datasource(), 'billing', 'UPDATE a SET x = 1', schema='report')
        self.assertEqual(mock_write.call_args.kwargs['schema'], 'report')

    @patch('sqlaudit.db_executor.mssql_executor.execute_read', return_value=(True, [], [], 0, 5, None))
    def test_execute_query_passes_schema_and_limit(self, mock_read):
        db_executor.execute_query(build_datasource(), 'billing', 'SELECT 1', limit=50, schema='report')
        self.assertEqual(mock_read.call_args.kwargs['schema'], 'report')
        self.assertEqual(mock_read.call_args.kwargs['limit'], 50)

    def test_demo_datasource_short_circuits(self):
        datasource = build_datasource(name='billing-prod-mssql')
        success, message = db_executor.test_connection(datasource)
        self.assertTrue(success)
        self.assertIn('模拟', message)
        self.assertEqual(db_executor.get_databases(datasource), ['billing_center', 'settlement'])
        self.assertEqual(db_executor.get_schemas(datasource, 'billing_center'), ['dbo', 'report'])

    def test_mysql_dispatch_is_unchanged(self):
        with patch('sqlaudit.db_executor._get_mysql_databases', return_value=['app']) as mock_mysql:
            self.assertEqual(db_executor.get_databases(DataSource(db_type='mysql', name='x')), ['app'])
            mock_mysql.assert_called_once()
