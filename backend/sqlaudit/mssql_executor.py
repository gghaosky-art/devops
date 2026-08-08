"""
SQL Server 执行器。驱动为 pymssql，仅支持 SQL 认证（不支持 Azure AD）。

关于只读边界的定位：PostgreSQL 可以用 SET TRANSACTION READ ONLY 让数据库自己
兜底，文本校验只是提前给个友好报错；**SQL Server 没有对应机制**——隔离级别不阻止
写入，ApplicationIntent=ReadOnly 只对 AlwaysOn 可读副本有效。因此这里的文本校验
是真防线，判定一律从严：宁可拒绝可疑写法让用户改写，也不放行。

即便如此，文本校验仍是第二层。第一层必须是数据源账号权限——查询用数据源应当配
db_datareader 角色的登录名。任何只靠解析 SQL 来保证只读的方案都挡不住动态 SQL。
"""
import logging
import re
import time

from .statements import normalize_for_rules, split_statements

try:
    import pymssql
except ImportError:  # pragma: no cover
    pymssql = None

logger = logging.getLogger(__name__)

DB_TYPE = 'sqlserver'
DEFAULT_SCHEMA = 'dbo'

MSSQL_SYSTEM_DATABASES = {'master', 'tempdb', 'model', 'msdb'}

# db_* 是固定数据库角色自带的 schema，guest / sys / INFORMATION_SCHEMA 同理，
# 都不是业务 schema。
MSSQL_SYSTEM_SCHEMAS = {
    'sys', 'INFORMATION_SCHEMA', 'guest',
    'db_owner', 'db_accessadmin', 'db_securityadmin', 'db_ddladmin',
    'db_backupoperator', 'db_datareader', 'db_datawriter',
    'db_denydatareader', 'db_denydatawriter',
}

# 允许的语句开头。T-SQL 没有 SHOW / DESC（那是 MySQL 语法），元数据查询走
# INFORMATION_SCHEMA 或 sys 视图，本身就是 SELECT。
_READ_PREFIX_RE = re.compile(r'^\s*(?:\(|SELECT\b|WITH\b)')

# 顺序有意义：先判定明确的写操作，再判定 INTO。否则
# WITH c AS (...) INSERT INTO t ... 会先命中 INTO，报出「SELECT ... INTO」这种
# 对不上号的提示。
_FORBIDDEN_PATTERNS = [
    (
        re.compile(r'\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE)\b'),
        '查询工单不允许写操作。注意 T-SQL 的 CTE 可以作为写入目标，'
        'WITH ... AS (...) DELETE 这类写法同样会被拒绝。',
    ),
    (
        # SELECT ... INTO 会建表并写入，却以 SELECT 开头，前缀判断放得过去
        re.compile(r'\bINTO\b'),
        'SELECT ... INTO 会创建新表并写入数据，查询工单不允许。',
    ),
    (
        re.compile(r'\b(?:CREATE|ALTER|DROP)\b'),
        '查询工单不允许 DDL 操作，请改提变更工单。',
    ),
    (
        re.compile(r'\b(?:EXEC|EXECUTE)\b'),
        '查询工单不允许执行存储过程或动态 SQL，它们能绕过一切文本校验。',
    ),
    (
        re.compile(r'\b(?:OPENROWSET|OPENQUERY|OPENDATASOURCE|OPENXML)\b'),
        '查询工单不允许访问外部数据源或链接服务器。',
    ),
    (
        re.compile(r'\bXP_\w+'),
        '查询工单不允许调用扩展存储过程。',
    ),
    (
        re.compile(r'\b(?:GRANT|REVOKE|DENY)\b'),
        '查询工单不允许变更权限。',
    ),
    (
        re.compile(r'\b(?:BACKUP|RESTORE|SHUTDOWN|KILL|DBCC|RECONFIGURE)\b'),
        '查询工单不允许实例级操作。',
    ),
    (
        re.compile(r'\b(?:BULK|WRITETEXT|UPDATETEXT)\b'),
        '查询工单不允许批量导入或大对象写入。',
    ),
]


def validate_query(sql_content):
    """
    校验查询工单内容是否只读，返回错误文案，None 表示通过。

    逐条语句判定而不是只看整段开头：SELECT 1; EXEC sp_foo 这种整段以 SELECT
    开头，只查开头会漏掉后半段。
    """
    statements = split_statements(sql_content, DB_TYPE)
    if not statements:
        return '查询内容不能为空。'

    for statement in statements:
        error = _check_read_only(statement)
        if error:
            return error

    return None


def _check_read_only(statement):
    normalized = normalize_for_rules(statement, DB_TYPE).upper()

    if not _READ_PREFIX_RE.match(normalized):
        return '查询工单只允许 SELECT 语句或以 WITH 开头的 CTE 查询。'

    for pattern, message in _FORBIDDEN_PATTERNS:
        if pattern.search(normalized):
            return message

    return None


def _ensure_driver():
    if pymssql is None:
        raise RuntimeError('未安装 pymssql，无法连接 SQL Server 数据源')


def _connect(datasource, database=None, as_dict=False, timeout=10, autocommit=False):
    """
    建立 pymssql 连接。

    刻意忽略 datasource.charset：那个字段是给 MySQL 用的，默认值 utf8mb4 不是
    合法的 FreeTDS 字符集名，原样传进来会直接连不上。SQL Server 侧统一走 UTF-8。
    """
    _ensure_driver()
    kwargs = {
        'server': datasource.host,
        'port': int(datasource.port or 1433),
        'user': datasource.user,
        'password': datasource.password,
        'charset': 'UTF-8',
        'login_timeout': timeout,
        'timeout': timeout,
        'as_dict': as_dict,
        'autocommit': autocommit,
    }
    if database:
        kwargs['database'] = database
    return pymssql.connect(**kwargs)


def test_connection(datasource):
    try:
        conn = _connect(datasource, timeout=5)
        conn.close()
        return True, '连接成功'
    except Exception as exc:
        return False, f'连接失败: {exc}'


def list_databases(datasource):
    """state = 0 只取 ONLINE 的库，恢复中或离线的库连不上，列出来只会误导。"""
    try:
        conn = _connect(datasource, timeout=5)
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT name FROM sys.databases WHERE state = 0 ORDER BY name')
                databases = [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()
        return [item for item in databases if item not in MSSQL_SYSTEM_DATABASES]
    except Exception as exc:
        logger.warning('list sqlserver databases failed on %s: %s', datasource.host, exc)
        return []


def list_schemas(datasource, database):
    try:
        conn = _connect(datasource, database=database, timeout=5)
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT name FROM sys.schemas ORDER BY name')
                schemas = [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()
        business = [item for item in schemas if item not in MSSQL_SYSTEM_SCHEMAS]
        return business or [DEFAULT_SCHEMA]
    except Exception as exc:
        logger.warning('list sqlserver schemas failed on %s/%s: %s', datasource.host, database, exc)
        return []


def execute_read(datasource, database, sql_content, schema=None, limit=200):
    start = time.time()
    conn = None
    try:
        # 刻意不开 autocommit：连接在事务里跑，close 时未提交的变更会被回滚。
        # 万一只读校验被绕过（比如动态 SQL），这层还能把写入撤掉。
        conn = _connect(datasource, database=database, as_dict=True, timeout=10)
        with conn.cursor() as cursor:
            cursor.execute(sql_content)
            rows = cursor.fetchmany(limit)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
        duration = int((time.time() - start) * 1000)
        # 行数取 len(rows) 而不是 cursor.rowcount：pymssql 对 SELECT 常返回 -1
        return True, columns, list(rows), len(rows), duration, None
    except Exception as exc:
        duration = int((time.time() - start) * 1000)
        return False, [], [], 0, duration, str(exc)
    finally:
        if conn is not None:
            conn.close()


def execute_write(datasource, database, sql_content, schema=None):
    """
    逐条执行并累加影响行数。

    与 MySQL 路径不同的是这里的事务是有意义的：SQL Server 的 DDL 可以回滚，
    失败时 rollback 能把整批变更一起撤掉，而 MySQL 的 DDL 会隐式提交。
    """
    start = time.time()
    statements = split_statements(sql_content, DB_TYPE)
    if not statements:
        return False, 0, 0, '执行失败: SQL 内容为空'

    conn = None
    try:
        conn = _connect(datasource, database=database, timeout=10, autocommit=False)
    except Exception as exc:
        duration = int((time.time() - start) * 1000)
        return False, 0, duration, f'连接失败: {exc}'

    total_affected = 0
    logs = []
    if schema:
        logs.append(f'目标 schema: {schema}')

    try:
        with conn.cursor() as cursor:
            for index, statement in enumerate(statements, 1):
                cursor.execute(statement)
                affected = cursor.rowcount
                total_affected += max(affected, 0)
                logs.append(f'语句 #{index}: 影响 {affected} 行')
        conn.commit()
        duration = int((time.time() - start) * 1000)
        return True, total_affected, duration, '\n'.join(logs)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:  # pragma: no cover - 回滚本身失败时保留原始错误
            logger.warning('sqlserver rollback failed on %s/%s', datasource.host, database)
        duration = int((time.time() - start) * 1000)
        return False, 0, duration, f'执行失败: {exc}'
    finally:
        conn.close()
