"""
切分器与多语句检测的用例。

MySQL 路径是既有行为，重写后允许且仅允许下面四处差异，全部是修复：

1. 行注释（-- 和 #）内的分号不再参与切分
2. 反引号标识符内的分号不再参与切分（旧实现只认 ' 和 "，反引号被当普通字符）
3. 反斜杠转义生效（旧实现把 \\' 当成闭合引号，引号状态会算反）
4. 空片段被丢弃，不再占用「语句 #N」的编号

其余必须逐字保持，所以下面 MySQL 与 SQL Server 的用例是成对写的。
"""
from django.test import SimpleTestCase

from .sql_checker import check_sql
from .statements import detect_multi_statement, split_statements


class SplitStatementsMySQLTests(SimpleTestCase):
    def test_splits_on_semicolon(self):
        self.assertEqual(
            split_statements('SELECT 1; SELECT 2;', 'mysql'),
            ['SELECT 1', 'SELECT 2'],
        )

    def test_ignores_semicolon_inside_string(self):
        self.assertEqual(
            split_statements("SELECT 'a;b'; SELECT 2", 'mysql'),
            ["SELECT 'a;b'", 'SELECT 2'],
        )

    def test_ignores_semicolon_inside_backtick_identifier(self):
        self.assertEqual(
            split_statements('SELECT * FROM `we;ird`; SELECT 2', 'mysql'),
            ['SELECT * FROM `we;ird`', 'SELECT 2'],
        )

    def test_drops_empty_segments(self):
        self.assertEqual(split_statements(';;SELECT 1;;', 'mysql'), ['SELECT 1'])

    def test_polardb_shares_mysql_profile(self):
        self.assertEqual(
            split_statements("SELECT 'a;b'; SELECT 2", 'polardb'),
            ["SELECT 'a;b'", 'SELECT 2'],
        )

    def test_unknown_db_type_falls_back_to_mysql(self):
        self.assertEqual(split_statements('SELECT 1; SELECT 2', 'nosuchdb'), ['SELECT 1', 'SELECT 2'])

    # ---- 以下两条是本次修复的行为差异 ----

    def test_semicolon_inside_line_comment_no_longer_splits(self):
        statements = split_statements(
            'DELETE FROM t WHERE id = 1; -- 备注; 还有\nSELECT 1',
            'mysql',
        )
        self.assertEqual(len(statements), 2)
        self.assertEqual(statements[0], 'DELETE FROM t WHERE id = 1')
        self.assertIn('SELECT 1', statements[1])

    def test_hash_comment_is_recognised(self):
        self.assertEqual(
            split_statements('SELECT 1 # 注释;里的分号\nSELECT 2', 'mysql'),
            ['SELECT 1 # 注释;里的分号\nSELECT 2'],
        )

    def test_double_dash_without_space_is_not_a_comment(self):
        # MySQL 要求 -- 后跟空白才算注释，1--2 是两个负号
        self.assertEqual(
            split_statements('SELECT 1--2;SELECT 3', 'mysql'),
            ['SELECT 1--2', 'SELECT 3'],
        )

    def test_backslash_escape_keeps_string_open(self):
        # 旧实现把 \\' 当成闭合引号，引号状态算反，后面的分号反而不切
        self.assertEqual(
            split_statements("SELECT 'quote\\'inside'; SELECT 2", 'mysql'),
            ["SELECT 'quote\\'inside'", 'SELECT 2'],
        )


class SplitStatementsSQLServerTests(SimpleTestCase):
    def test_double_dash_without_space_is_a_comment(self):
        # 与 MySQL 相反：T-SQL 的 -- 后面不需要空白
        self.assertEqual(
            split_statements('SELECT 1--2;SELECT 3', 'sqlserver'),
            ['SELECT 1--2;SELECT 3'],
        )

    def test_ignores_semicolon_inside_bracket_identifier(self):
        self.assertEqual(
            split_statements('SELECT * FROM [dbo].[a;b]; SELECT 2', 'sqlserver'),
            ['SELECT * FROM [dbo].[a;b]', 'SELECT 2'],
        )

    def test_handles_doubled_bracket_escape(self):
        self.assertEqual(
            split_statements('SELECT * FROM [we]]ird;name]; SELECT 2', 'sqlserver'),
            ['SELECT * FROM [we]]ird;name]', 'SELECT 2'],
        )

    def test_handles_doubled_quote_escape(self):
        self.assertEqual(
            split_statements("SELECT 'it''s; ok'; SELECT 2", 'sqlserver'),
            ["SELECT 'it''s; ok'", 'SELECT 2'],
        )

    def test_backslash_is_not_an_escape(self):
        # T-SQL 里反斜杠不转义，字符串在下一个单引号处就结束了
        self.assertEqual(
            split_statements("SELECT 'a\\'; SELECT 2", 'sqlserver'),
            ["SELECT 'a\\'", 'SELECT 2'],
        )

    def test_go_separates_batches(self):
        script = 'UPDATE t SET x = 1\nGO\nUPDATE t SET x = 2\nGO 3\n'
        self.assertEqual(
            split_statements(script, 'sqlserver'),
            ['UPDATE t SET x = 1', 'UPDATE t SET x = 2'],
        )

    def test_go_is_case_insensitive_and_tolerates_whitespace(self):
        self.assertEqual(
            split_statements('SELECT 1\n   go   \nSELECT 2', 'sqlserver'),
            ['SELECT 1', 'SELECT 2'],
        )

    def test_inline_go_is_not_a_separator(self):
        # 只有独占一行的 GO 才是批次分隔符
        self.assertEqual(
            split_statements('SELECT go FROM t', 'sqlserver'),
            ['SELECT go FROM t'],
        )

    def test_go_inside_comment_is_ignored(self):
        self.assertEqual(
            split_statements('SELECT 1\n/*\nGO\n*/\nSELECT 2', 'sqlserver'),
            ['SELECT 1\n/*\nGO\n*/\nSELECT 2'],
        )

    def test_nested_block_comment(self):
        script = 'SELECT 1 /* a /* b */ ; c */ SELECT 2'
        # T-SQL 块注释可嵌套，整段都是注释，里面的分号不切
        self.assertEqual(split_statements(script, 'sqlserver'), [script])
        # MySQL 不嵌套，注释在第一个 */ 处结束，分号回到代码位置
        self.assertEqual(len(split_statements(script, 'mysql')), 2)

    def test_procedure_body_semicolons_do_not_split(self):
        script = (
            'CREATE PROCEDURE p AS\n'
            'BEGIN\n'
            '    SELECT 1;\n'
            '    SELECT 2;\n'
            'END'
        )
        self.assertEqual(split_statements(script, 'sqlserver'), [script])

    def test_begin_transaction_is_not_a_block(self):
        script = 'BEGIN TRANSACTION\nUPDATE t SET x = 1;\nCOMMIT;'
        self.assertEqual(
            split_statements(script, 'sqlserver'),
            ['BEGIN TRANSACTION\nUPDATE t SET x = 1', 'COMMIT'],
        )

    def test_case_end_does_not_close_outer_begin_block(self):
        script = (
            'CREATE PROCEDURE p AS\n'
            'BEGIN\n'
            "    UPDATE t SET s = CASE WHEN a = 1 THEN 'x' ELSE 'y' END;\n"
            '    SELECT 2;\n'
            'END'
        )
        self.assertEqual(split_statements(script, 'sqlserver'), [script])

    def test_standalone_case_end_still_splits(self):
        script = "UPDATE t SET s = CASE WHEN a = 1 THEN 'x' ELSE 'y' END; SELECT 2"
        statements = split_statements(script, 'sqlserver')
        self.assertEqual(len(statements), 2)
        self.assertTrue(statements[0].endswith('END'))


class DetectMultiStatementTests(SimpleTestCase):
    def test_detects_undelimited_updates(self):
        self.assertTrue(detect_multi_statement(
            'UPDATE a SET x = 1\nUPDATE b SET y = 2',
            'sqlserver',
        ))

    def test_detects_undelimited_deletes(self):
        self.assertTrue(detect_multi_statement(
            'DELETE FROM a WHERE id = 1\nDELETE FROM b WHERE id = 2',
            'sqlserver',
        ))

    def test_single_statement_is_not_flagged(self):
        self.assertFalse(detect_multi_statement(
            'UPDATE a SET x = 1 WHERE id = 2',
            'sqlserver',
        ))

    def test_insert_select_is_not_flagged(self):
        self.assertFalse(detect_multi_statement(
            'INSERT INTO t (a)\nSELECT a FROM s',
            'sqlserver',
        ))

    def test_update_with_set_on_next_line_is_not_flagged(self):
        self.assertFalse(detect_multi_statement(
            'UPDATE t\nSET x = 1\nWHERE id = 2',
            'sqlserver',
        ))

    def test_subquery_is_not_flagged(self):
        self.assertFalse(detect_multi_statement(
            'UPDATE t SET x = (\nSELECT MAX(id) FROM s\n) WHERE id = 1',
            'sqlserver',
        ))

    def test_statements_inside_begin_end_are_not_flagged(self):
        self.assertFalse(detect_multi_statement(
            'IF @x = 1\nBEGIN\n    UPDATE a SET x = 1\n    UPDATE b SET y = 2\nEND',
            'sqlserver',
        ))

    def test_merge_clauses_are_not_flagged(self):
        self.assertFalse(detect_multi_statement(
            'MERGE t AS tgt\n'
            'USING s AS src ON tgt.id = src.id\n'
            'WHEN MATCHED THEN UPDATE SET a = 1\n'
            'WHEN NOT MATCHED THEN INSERT (a) VALUES (1)',
            'sqlserver',
        ))

    def test_on_duplicate_key_update_is_not_flagged(self):
        self.assertFalse(detect_multi_statement(
            'INSERT INTO t (a) VALUES (1)\nON DUPLICATE KEY UPDATE a = 1',
            'mysql',
        ))

    def test_alter_table_drop_column_is_not_flagged(self):
        self.assertFalse(detect_multi_statement(
            'ALTER TABLE t\nDROP COLUMN c',
            'sqlserver',
        ))


class CheckSqlIntegrationTests(SimpleTestCase):
    def test_undelimited_script_reports_error(self):
        results = check_sql(
            'UPDATE a SET x = 1 WHERE id = 1\nUPDATE b SET y = 2 WHERE id = 2',
            'DML',
            'sqlserver',
        )
        self.assertTrue(any(item.rule_name == 'MULTI_STATEMENT_NO_DELIMITER' for item in results))

    def test_delimited_script_is_checked_per_statement(self):
        results = check_sql(
            'UPDATE a SET x = 1;\nDELETE FROM b;',
            'DML',
            'sqlserver',
        )
        self.assertFalse(any(item.rule_name == 'MULTI_STATEMENT_NO_DELIMITER' for item in results))
        rules = {item.rule_name for item in results}
        self.assertIn('NO_WHERE_UPDATE', rules)
        self.assertIn('NO_WHERE_DELETE', rules)

    def test_mysql_per_statement_rules_still_apply(self):
        results = check_sql('DELETE FROM t', 'DML', 'mysql')
        self.assertTrue(any(item.rule_name == 'NO_WHERE_DELETE' for item in results))

    def test_bracket_quoted_table_name_is_parsed(self):
        results = check_sql('CREATE TABLE [dbo].[9tab] (id int)', 'DDL', 'sqlserver')
        self.assertTrue(any(item.rule_name == 'TABLE_NAME_CONVENTION' for item in results))

    def test_backtick_quoted_table_name_still_parsed(self):
        results = check_sql('CREATE TABLE `9tab` (id int)', 'DDL', 'mysql')
        self.assertTrue(any(item.rule_name == 'TABLE_NAME_CONVENTION' for item in results))

    def test_clean_statement_passes(self):
        results = check_sql('UPDATE t SET x = 1 WHERE id = 2', 'DML', 'sqlserver')
        self.assertEqual([item.rule_name for item in results], ['ALL_PASSED'])
