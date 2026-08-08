"""
SQL Server 查询工单只读校验的用例。

这道校验在 SQL Server 上是硬防线（没有 SET TRANSACTION READ ONLY 可依赖），
所以拒绝规则表要求逐条覆盖，不接受抽样。放行用例同样重要——误报会挡住正常查询。
"""
from django.test import SimpleTestCase

from . import db_executor, mssql_executor
from .models import DataSource


class MssqlReadOnlyAllowTests(SimpleTestCase):
    def assertAllowed(self, sql):
        self.assertIsNone(mssql_executor.validate_query(sql), f'不应被拒绝: {sql}')

    def test_plain_select(self):
        self.assertAllowed('SELECT id, name FROM orders WHERE status = 1')

    def test_cte_query(self):
        self.assertAllowed('WITH c AS (SELECT id FROM orders) SELECT * FROM c')

    def test_parenthesised_select(self):
        self.assertAllowed('(SELECT 1)')

    def test_information_schema_query(self):
        self.assertAllowed("SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo'")

    def test_multiple_reads(self):
        self.assertAllowed('SELECT 1; SELECT 2')

    def test_subquery_with_in_is_not_mistaken_for_into(self):
        self.assertAllowed('SELECT * FROM t WHERE x IN (SELECT y FROM s)')

    def test_keyword_inside_string_literal(self):
        self.assertAllowed("SELECT * FROM t WHERE name = 'INTO'")

    def test_keyword_inside_bracket_identifier(self):
        self.assertAllowed('SELECT [Delete], [Into] FROM t')

    def test_keyword_as_identifier_substring(self):
        # create_date / dm_exec_sessions 里的下划线是词字符，\b 不该在这里断开
        self.assertAllowed('SELECT create_date FROM sys.databases')
        self.assertAllowed('SELECT * FROM sys.dm_exec_sessions')

    def test_keyword_inside_line_comment(self):
        self.assertAllowed('SELECT 1 -- DROP TABLE t')

    def test_keyword_inside_block_comment(self):
        self.assertAllowed('SELECT * FROM t /* INTO staging */')

    def test_semicolon_inside_string_does_not_create_second_statement(self):
        self.assertAllowed("SELECT '; DROP TABLE t' AS payload")

    def test_leading_semicolon_before_cte(self):
        # ;WITH 是 T-SQL 常见写法，前导空片段被丢弃后仍是一条合法只读查询
        self.assertAllowed(';WITH c AS (SELECT * FROM t) SELECT * FROM c')

    def test_table_hint_with_clause(self):
        self.assertAllowed('SELECT TOP 10 * FROM t WITH (NOLOCK)')

    def test_write_buried_in_nested_comment_stays_commented_out(self):
        # T-SQL 块注释可嵌套：内层 */ 只把深度降到 1，DROP 仍在注释里，
        # 服务端不会执行，因此放行是对的
        self.assertAllowed('SELECT 1 /* a /* */ DROP TABLE t */')


class MssqlReadOnlyRejectTests(SimpleTestCase):
    def assertRejected(self, sql, expect_keyword=None):
        error = mssql_executor.validate_query(sql)
        self.assertIsNotNone(error, f'应被拒绝: {sql}')
        if expect_keyword:
            self.assertIn(expect_keyword, error)
        return error

    def test_select_into_creates_a_table(self):
        self.assertRejected('SELECT * INTO staging_orders FROM orders', 'INTO')

    def test_cte_as_delete_target(self):
        error = self.assertRejected('WITH c AS (SELECT * FROM orders) DELETE FROM c')
        self.assertIn('CTE', error)

    def test_cte_as_update_target(self):
        self.assertRejected('WITH c AS (SELECT * FROM orders) UPDATE c SET status = 1')

    def test_plain_write_statements(self):
        self.assertRejected('UPDATE orders SET status = 1')
        self.assertRejected('DELETE FROM orders')
        self.assertRejected('INSERT INTO orders (id) VALUES (1)')
        self.assertRejected('MERGE orders AS t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET a = 1')
        self.assertRejected('TRUNCATE TABLE orders')

    def test_ddl(self):
        self.assertRejected('DROP TABLE orders')
        self.assertRejected('CREATE TABLE t (id int)')
        self.assertRejected('ALTER TABLE t ADD c int')

    def test_stored_procedure_execution(self):
        self.assertRejected('EXEC sp_who')
        self.assertRejected("EXECUTE sp_executesql N'SELECT 1'")

    def test_extended_stored_procedure(self):
        self.assertRejected('SELECT * FROM t WHERE id = xp_foo()', '扩展存储过程')

    def test_external_data_sources(self):
        self.assertRejected("SELECT * FROM OPENQUERY(srv, 'SELECT 1')", '外部数据源')
        self.assertRejected("SELECT * FROM OPENROWSET('SQLNCLI', 'srv', 'SELECT 1')", '外部数据源')

    def test_permission_changes(self):
        self.assertRejected('GRANT SELECT ON orders TO app_user')
        self.assertRejected('REVOKE SELECT ON orders FROM app_user')

    def test_instance_level_operations(self):
        self.assertRejected("BACKUP DATABASE app TO DISK = 'x'")
        self.assertRejected('DBCC CHECKDB')
        self.assertRejected('SHUTDOWN')

    def test_bulk_and_lob_writes(self):
        self.assertRejected("BULK INSERT t FROM 'f.csv'")
        self.assertRejected("WRITETEXT t.c @ptr 'x'")

    def test_write_hidden_after_a_leading_select(self):
        # 只看整段开头会漏掉后半段
        self.assertRejected('SELECT 1; DROP TABLE orders')
        self.assertRejected('SELECT 1; EXEC sp_who')

    def test_write_hidden_after_a_go_batch(self):
        self.assertRejected('SELECT 1\nGO\nDELETE FROM orders')

    def test_write_without_any_delimiter(self):
        # T-SQL 分号可选，两条语句挤在一起也能执行
        self.assertRejected('SELECT 1 DELETE FROM orders')

    def test_keyword_split_by_comment(self):
        # 注释归一化成空格后 DEL ETE 不再是关键字，但也不再以 SELECT 开头
        self.assertRejected('SELECT 1; DEL/**/ETE FROM orders')

    def test_write_after_empty_statements(self):
        self.assertRejected('SELECT 1;;; DROP TABLE orders')

    def test_non_read_prefix(self):
        self.assertRejected('SET NOCOUNT ON', '只允许 SELECT')
        self.assertRejected('USE master', '只允许 SELECT')
        self.assertRejected('PRINT 1', '只允许 SELECT')

    def test_empty_content(self):
        self.assertRejected('', '不能为空')
        self.assertRejected('   \n  ', '不能为空')


class ValidateQueryContentDispatchTests(SimpleTestCase):
    def test_sqlserver_datasource_uses_mssql_rules(self):
        datasource = DataSource(db_type='sqlserver')
        self.assertIsNone(db_executor.validate_query_content(datasource, 'SELECT 1'))
        self.assertIn(
            'INTO',
            db_executor.validate_query_content(datasource, 'SELECT * INTO t2 FROM t'),
        )

    def test_mysql_datasource_keeps_existing_rule(self):
        datasource = DataSource(db_type='mysql')
        self.assertEqual(
            db_executor.validate_query_content(datasource, 'UPDATE orders SET status = 1'),
            '查询工单只允许 SELECT / SHOW / DESC 语句',
        )
        self.assertIsNone(db_executor.validate_query_content(datasource, 'SHOW TABLES'))
