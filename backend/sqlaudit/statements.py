"""
SQL 语句切分。

MySQL 与 SQL Server 的词法差异较大，用同一个状态机 + 方言参数驱动：
  - 标识符引号：MySQL 用反引号，SQL Server 用方括号，两者都支持双引号
  - 字符串转义：MySQL 额外支持反斜杠，SQL Server 只有 '' 双写
  - 行注释：MySQL 的 -- 必须跟空白才算注释（--1 是减负号），SQL Server 无此要求；
    另外 # 只有 MySQL 认
  - 块注释：SQL Server 允许嵌套，MySQL 不允许
  - 批次分隔：GO 是 SSMS/sqlcmd 的客户端指令，不是 T-SQL 语法，原样发给服务端
    会报语法错，必须在切分阶段剥掉

T-SQL 还有两个 MySQL 没有的麻烦：

1. 存储过程体里的分号不是语句分隔符。MySQL 靠 DELIMITER 切换分隔符，T-SQL 没有
   对应机制，只能靠识别 BEGIN...END 块。因此 sqlserver 方言下维护块栈，块内的
   分号不参与切分。

2. 分号本身是可选的，脚本可能一条分号都没有。这种情况不做启发式切分——切错会把
   半条 SQL 发到生产库，而漏检只是让用户补个分号。切分器只认明确分隔符，另由
   detect_multi_statement 识别后在检查规则里报错要求补齐。

拿不准时一律「不切」：不切最坏是整段当一条语句发给服务端（T-SQL 本就接受多语句
批次），切错则可能执行半条 SQL。
"""
import re


GO_BATCH_RE = re.compile(r'^\s*GO(?:\s+\d+)?\s*$', re.IGNORECASE)

# 词法产物的分类。只有 CODE 位置的分号才是语句分隔符。
CODE = 'code'
STRING = 'string'
IDENT = 'ident'
COMMENT = 'comment'
BATCH = 'batch'

_MYSQL_PROFILE = {
    'ident_quotes': {'`': '`', '"': '"'},
    'backslash_escape': True,
    'hash_line_comment': True,
    'line_comment_requires_space': True,
    'nested_block_comment': False,
    'batch_separator': None,
    'track_blocks': False,
}

_SQLSERVER_PROFILE = {
    'ident_quotes': {'[': ']', '"': '"'},
    'backslash_escape': False,
    'hash_line_comment': False,
    'line_comment_requires_space': False,
    'nested_block_comment': True,
    'batch_separator': GO_BATCH_RE,
    'track_blocks': True,
}

DIALECT_PROFILES = {
    'mysql': _MYSQL_PROFILE,
    'polardb': _MYSQL_PROFILE,
    'sqlserver': _SQLSERVER_PROFILE,
}

# BEGIN 后面跟这些词时不是语句块，而是事务控制，不该压栈。
_NON_BLOCK_BEGIN_FOLLOWERS = {'TRANSACTION', 'TRAN', 'DISTRIBUTED'}

# CASE ... END 与 BEGIN ... END 共用 END 收尾，两者都要压栈才能配平。
_BLOCK_OPENERS = {'BEGIN', 'CASE'}

# 只统计 DML 起始关键字。这条规则存在的意义是保护 NO_WHERE_DELETE /
# NO_WHERE_UPDATE 这类逐句规则不被「整段无分号」绕过，而它们本就只针对 DML。
# 把 DDL 关键字也算进来只会带来误报——ALTER TABLE t DROP COLUMN c 会被数成两条。
# SELECT / WITH / SET / DECLARE 同样不计入：它们都可能是上一条语句的延续
# （INSERT ... SELECT、UPDATE 换行 SET、CTE 后接语句）。
_STATEMENT_STARTERS = {'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'EXEC', 'EXECUTE'}

# 前一个词是这些时，后面的 DML 关键字属于上一条语句的语法成分，不是新语句：
#   MySQL   INSERT ... ON DUPLICATE KEY UPDATE
#   T-SQL   MERGE ... WHEN MATCHED THEN UPDATE / THEN INSERT / THEN DELETE
_CONTINUATION_WORDS = {'THEN', 'KEY', 'ELSE', 'AND', 'OR', 'NOT', 'AS', 'WHEN', 'UNION', 'FOR'}


def get_profile(db_type):
    """未知类型按 MySQL 处理，与 db_executor 的默认取值保持一致。"""
    return DIALECT_PROFILES.get((db_type or 'mysql').strip().lower(), _MYSQL_PROFILE)


def split_statements(sql_content, db_type='mysql'):
    """
    按分号与批次分隔符切分 SQL，返回去掉首尾空白后的非空语句列表。

    注释、字符串字面量、带引号的标识符内部的分号都不参与切分；sqlserver 下
    BEGIN...END 块内的分号同样不参与。
    """
    profile = get_profile(db_type)
    statements = []
    current = []
    tracker = _BlockTracker(profile['track_blocks'])

    for kind, char in lex(sql_content, profile):
        if kind == BATCH:
            tracker.reset()
            _flush(statements, current)
            continue

        if kind == CODE:
            tracker.feed(char)
            if char == ';' and not tracker.inside_block:
                tracker.reset()
                _flush(statements, current)
                continue

        current.append(char)

    tracker.close()
    _flush(statements, current)
    return statements


def detect_multi_statement(sql_content, db_type='mysql'):
    """
    判断一个切分后的片段里是否疑似塞了多条语句。

    只在片段完全没有分隔符时才有意义——有分号或 GO 的话 split_statements 已经切开
    了。判定刻意收得很紧，只认「独占一行开头、且前一个词不是语法延续」的 DML 关键
    字：这条规则是 error 级、会挡住提交，误报的代价比漏报高。漏掉的场景（比如两条
    语句挤在同一行）交由数据库自己报语法错。
    """
    profile = get_profile(db_type)
    tracker = _BlockTracker(profile['track_blocks'])
    paren_depth = 0
    word = []
    starters = 0
    prev_word = ''
    at_line_start = True
    word_at_line_start = True

    def take_word():
        nonlocal starters, prev_word
        if not word:
            return
        text = ''.join(word).upper()
        word.clear()
        tracker.feed_word(text)
        if (
            word_at_line_start
            and paren_depth == 0
            and not tracker.inside_block
            and text in _STATEMENT_STARTERS
            and prev_word not in _CONTINUATION_WORDS
        ):
            starters += 1
        prev_word = text

    for kind, char in lex(sql_content, profile):
        if kind != CODE:
            take_word()
            continue

        if char.isalnum() or char == '_':
            if not word:
                word_at_line_start = at_line_start
            word.append(char)
            at_line_start = False
            continue

        take_word()
        if char == '\n':
            at_line_start = True
        elif not char.isspace():
            at_line_start = False

        if char == '(':
            paren_depth += 1
        elif char == ')':
            paren_depth = max(paren_depth - 1, 0)

    take_word()
    return starters >= 2


def lex(sql_content, profile):
    """
    逐字符产出 (kind, char)。kind 为 BATCH 时 char 为空串，表示一个批次分隔点。

    调用方据 kind 判断该字符是否处于可解析的代码位置。
    """
    text = sql_content or ''
    length = len(text)
    ident_quotes = profile['ident_quotes']
    backslash_escape = profile['backslash_escape']
    hash_line_comment = profile['hash_line_comment']
    comment_needs_space = profile['line_comment_requires_space']
    nested_block_comment = profile['nested_block_comment']
    batch_separator = profile['batch_separator']

    index = 0
    at_line_start = True

    while index < length:
        char = text[index]

        # GO 只在独占一行时才是批次分隔符，行内出现的 GO 是普通标识符
        if batch_separator is not None and at_line_start:
            line_end = text.find('\n', index)
            if line_end == -1:
                line_end = length
            if batch_separator.match(text[index:line_end]):
                yield BATCH, ''
                index = line_end + 1
                at_line_start = True
                continue

        if _starts_line_comment(text, index, char, hash_line_comment, comment_needs_space):
            end = text.find('\n', index)
            if end == -1:
                end = length
            for skipped in text[index:end]:
                yield COMMENT, skipped
            index = end
            at_line_start = False
            continue

        if text.startswith('/*', index):
            index = yield from _lex_block_comment(text, index, nested_block_comment)
            at_line_start = False
            continue

        if char == "'":
            index = yield from _lex_quoted(text, index, "'", STRING, backslash_escape)
            at_line_start = False
            continue

        if char in ident_quotes:
            index = yield from _lex_quoted(text, index, ident_quotes[char], IDENT, backslash_escape)
            at_line_start = False
            continue

        yield CODE, char
        at_line_start = char == '\n'
        index += 1


def _starts_line_comment(text, index, char, hash_line_comment, needs_space):
    if hash_line_comment and char == '#':
        return True
    if not text.startswith('--', index):
        return False
    if not needs_space:
        return True
    # MySQL 要求 -- 后跟空白才算注释，否则 1--2 会被当成注释
    following = text[index + 2:index + 3]
    return following == '' or following.isspace()


def _lex_block_comment(text, index, nested):
    length = len(text)
    depth = 1
    yield COMMENT, '/'
    yield COMMENT, '*'
    index += 2

    while index < length and depth > 0:
        if nested and text.startswith('/*', index):
            depth += 1
            yield COMMENT, '/'
            yield COMMENT, '*'
            index += 2
            continue
        if text.startswith('*/', index):
            depth -= 1
            yield COMMENT, '*'
            yield COMMENT, '/'
            index += 2
            continue
        yield COMMENT, text[index]
        index += 1

    return index


def _lex_quoted(text, index, closing, kind, backslash_escape):
    """
    消费一段引号包裹的内容，返回结束后的下标。

    双写（'' / ]] / ""）是通用转义，反斜杠转义只有 MySQL 有。未闭合时消费到末尾，
    交由数据库去报语法错，切分阶段不做判断。
    """
    length = len(text)
    yield kind, text[index]
    index += 1

    while index < length:
        char = text[index]
        if backslash_escape and char == '\\' and index + 1 < length:
            yield kind, char
            yield kind, text[index + 1]
            index += 2
            continue
        if char == closing:
            if text.startswith(closing * 2, index):
                yield kind, char
                yield kind, char
                index += 2
                continue
            yield kind, char
            return index + 1
        yield kind, char
        index += 1

    return index


class _BlockTracker:
    """
    跟踪 BEGIN...END / CASE...END 嵌套深度。

    MySQL 方言下整体停用（enabled=False），保证既有切分行为一字不改。
    """

    def __init__(self, enabled):
        self.enabled = enabled
        self.depth = 0
        self._word = []
        self._pending_begin = False

    @property
    def inside_block(self):
        return self.enabled and (self.depth > 0 or self._pending_begin)

    def feed(self, char):
        if not self.enabled:
            return
        if char.isalnum() or char == '_':
            self._word.append(char)
            return
        self.close_word()

    def feed_word(self, text):
        """detect_multi_statement 已经自己攒好了词，直接交过来。"""
        if not self.enabled:
            return
        self._apply(text)

    def close_word(self):
        if not self._word:
            return
        text = ''.join(self._word).upper()
        self._word.clear()
        self._apply(text)

    def _apply(self, text):
        if self._pending_begin:
            self._pending_begin = False
            # BEGIN TRANSACTION / BEGIN TRAN 不是语句块，不压栈
            if text not in _NON_BLOCK_BEGIN_FOLLOWERS:
                self.depth += 1

        if text == 'BEGIN':
            # 是不是语句块要看下一个词，先挂起
            self._pending_begin = True
        elif text == 'CASE':
            self.depth += 1
        elif text == 'END':
            self.depth = max(self.depth - 1, 0)

    def close(self):
        self.close_word()
        if self._pending_begin:
            self._pending_begin = False
            self.depth += 1

    def reset(self):
        self.depth = 0
        self._word.clear()
        self._pending_begin = False


def _flush(statements, current):
    statement = ''.join(current).strip()
    current.clear()
    if statement:
        statements.append(statement)
