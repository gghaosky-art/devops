export const SQL_AUDIT_SUPPORT_TEXT = '支持 MySQL、MongoDB、PolarDB、SQL Server'

// supportsSchema：库下面还有 schema 维度，需要多一级下拉
// usesCharset：连接需要字符集参数。MongoDB 没有这个概念，SQL Server 由驱动固定走
//   UTF-8，都不该让用户填
export const DATASOURCE_TYPE_OPTIONS = [
  { value: 'mysql', label: 'MySQL', defaultPort: 3306, supportsSchema: false, usesCharset: true },
  { value: 'mongodb', label: 'MongoDB', defaultPort: 27017, supportsSchema: false, usesCharset: false },
  { value: 'polardb', label: 'PolarDB', defaultPort: 3306, supportsSchema: false, usesCharset: true },
  { value: 'sqlserver', label: 'SQL Server', defaultPort: 1433, supportsSchema: true, usesCharset: false },
]

const TYPE_INDEX = DATASOURCE_TYPE_OPTIONS.reduce((result, item) => {
  result[item.value] = item
  return result
}, {})

export const DATASOURCE_TYPE_LABELS = DATASOURCE_TYPE_OPTIONS.reduce((result, item) => {
  result[item.value] = item.label
  return result
}, {})

export const DATASOURCE_DEFAULT_PORTS = DATASOURCE_TYPE_OPTIONS.reduce((result, item) => {
  result[item.value] = item.defaultPort
  return result
}, {})

export const DATASOURCE_KNOWN_PORTS = [...new Set(DATASOURCE_TYPE_OPTIONS.map(item => item.defaultPort))]

export const MONGODB_QUERY_SAMPLE = 'find {"collection":"orders","filter":{"status":"running"},"limit":50}'
export const MONGODB_WRITE_SAMPLE = 'updateMany {"collection":"orders","filter":{"status":"new"},"update":{"$set":{"status":"done"}}}'

function normalizeType(type) {
  return String(type || 'mysql').trim().toLowerCase()
}

export function getDatasourceTypeLabel(type) {
  return DATASOURCE_TYPE_LABELS[normalizeType(type)] || DATASOURCE_TYPE_LABELS.mysql
}

export function getDatasourceDefaultPort(type) {
  return DATASOURCE_DEFAULT_PORTS[normalizeType(type)] || 3306
}

export function datasourceSupportsSchema(type) {
  return Boolean(TYPE_INDEX[normalizeType(type)]?.supportsSchema)
}

export function datasourceUsesCharset(type) {
  return TYPE_INDEX[normalizeType(type)]?.usesCharset !== false
}

export function getQueryPlaceholder(type) {
  if (normalizeType(type) === 'mongodb') {
    return `输入 MongoDB 查询命令，例如：${MONGODB_QUERY_SAMPLE}`
  }
  if (normalizeType(type) === 'sqlserver') {
    return '输入 SELECT 查询语句，或以 WITH 开头的 CTE 查询...'
  }
  return '输入 SELECT / SHOW / DESC 查询语句...'
}

export function getQueryHint(type) {
  if (normalizeType(type) === 'mongodb') {
    return 'MongoDB 查询支持 find / aggregate / count / distinct 四种命令格式'
  }
  if (normalizeType(type) === 'sqlserver') {
    // T-SQL 没有 SHOW / DESC，元数据查询走 INFORMATION_SCHEMA 视图
    return 'SQL Server 查询仅允许 SELECT 与 CTE（WITH ... SELECT）；'
      + 'SELECT ... INTO、EXEC 与 CTE 写入均会被拒绝'
  }
  return 'MySQL / PolarDB 查询仅允许 SELECT / SHOW / DESC 语句'
}

export function getOrderPlaceholder(type) {
  if (normalizeType(type) === 'mongodb') {
    return `输入 MongoDB 变更命令，例如：${MONGODB_WRITE_SAMPLE}`
  }
  return '输入 SQL 语句，多条语句以分号分隔...'
}

export function getOrderHint(type) {
  if (normalizeType(type) === 'mongodb') {
    return 'MongoDB 支持 insertOne / insertMany / updateOne / updateMany / deleteOne / deleteMany / createCollection / dropCollection / createIndex / dropIndex'
  }
  if (normalizeType(type) === 'sqlserver') {
    // T-SQL 的分号可选，整段没有分隔符时无法逐句审计，提交会被拦下
    return 'SQL Server 支持常见 DML、DDL 语句。多条语句请用分号或 GO 分隔，'
      + '否则无法逐句审计；存储过程体内的分号会被正确识别，无需额外处理'
  }
  return 'MySQL / PolarDB 支持常见 DML、DDL 语句'
}
