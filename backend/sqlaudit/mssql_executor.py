"""
SQL Server 执行器。驱动为 pymssql，仅支持 SQL 认证。

本模块目前只实现查询工单的只读校验，连接与执行在后续提交补齐。

关于只读边界的定位：PostgreSQL 可以用 SET TRANSACTION READ ONLY 让数据库自己
兜底，文本校验只是提前给个友好报错；**SQL Server 没有对应机制**——隔离级别不阻止
写入，ApplicationIntent=ReadOnly 只对 AlwaysOn 可读副本有效。因此这里的文本校验
是真防线，判定一律从严：宁可拒绝可疑写法让用户改写，也不放行。

即便如此，文本校验仍是第二层。第一层必须是数据源账号权限——查询用数据源应当配
db_datareader 角色的登录名。任何只靠解析 SQL 来保证只读的方案都挡不住动态 SQL。
"""
import re

from .statements import normalize_for_rules, split_statements


DB_TYPE = 'sqlserver'

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
