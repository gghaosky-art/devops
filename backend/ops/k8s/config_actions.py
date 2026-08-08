"""
K8sClusterViewSet 的 config 相关 action。

从原 ops/k8s_views.py 拆出，逻辑未改动。
"""

import base64
from django.core.cache import cache
from ops.k8s_scope import resolve_scope
from rest_framework.decorators import action
from rest_framework.response import Response
from .cache import _get_or_set_resource_cache
from .client import K8S_DEMO_STATE_CACHE_TTL
from .demo import DEMO_CONFIGMAPS, DEMO_SECRETS, _demo_config_backup_key, _get_demo_state, _set_demo_state
from .items import _filter_by_ns
from .revisions import _build_text_diff, _config_backup_key, _config_revision_queryset, _create_config_revision, _dump_config_text, _normalize_config_text, _serialize_revision
from . import cache as _cache_mod
from . import client as _client_mod


class ConfigActionsMixin:
    @action(detail=True, methods=['get'])
    def configmaps(self, request, pk=None):
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            demo_items = _get_demo_state(cluster.id, 'configmaps', DEMO_CONFIGMAPS)
            return Response(_filter_by_ns(demo_items, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                items = (v1.list_config_map_for_all_namespaces() if namespace == '_all'
                         else v1.list_namespaced_config_map(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'data_count': len(i.data or {}),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'configmaps', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    @action(detail=True, methods=['get'])
    def secrets(self, request, pk=None):
        cluster = self.get_object()
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if _client_mod._is_demo(cluster):
            demo_items = _get_demo_state(cluster.id, 'secrets', DEMO_SECRETS)
            return Response(_filter_by_ns(demo_items, namespace))
        try:
            def loader():
                k8s = _client_mod._get_k8s_client(cluster)
                v1 = k8s.CoreV1Api()
                items = (v1.list_secret_for_all_namespaces() if namespace == '_all'
                         else v1.list_namespaced_secret(namespace=namespace)).items
                return [{'name': i.metadata.name, 'namespace': i.metadata.namespace,
                         'type': i.type or 'Opaque', 'data_count': len(i.data or {}),
                         'created': i.metadata.creation_timestamp.isoformat() if i.metadata.creation_timestamp else ''
                         } for i in items]

            data = _get_or_set_resource_cache(cluster, 'secrets', namespace, loader)
            return Response(data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)

    def _get_demo_config_resource(self, cluster, resource_type, namespace, name):
        cache_name = 'configmaps' if resource_type == 'configmap' else 'secrets'
        defaults = DEMO_CONFIGMAPS if resource_type == 'configmap' else DEMO_SECRETS
        items = _get_demo_state(cluster.id, cache_name, defaults)
        for item in items:
            if item.get('name') == name and item.get('namespace') == namespace:
                payload = item.get('data_payload')
                if payload is None:
                    payload = {f'key{i + 1}': f'value{i + 1}' for i in range(item.get('data_count', 1))}
                return {
                    'resource_type': resource_type,
                    'name': item.get('name', name),
                    'namespace': item.get('namespace', namespace),
                    'secret_type': item.get('type', 'Opaque'),
                    'data': payload,
                    'text': _dump_config_text(payload),
                    'updated_at': item.get('updated_at', ''),
                    'updated_by': item.get('updated_by', ''),
                }
        raise ValueError(f'Resource not found: {resource_type}/{namespace}/{name}')

    def _update_demo_config_resource(self, cluster, resource_type, namespace, name, data, username):
        import datetime as _dt

        cache_name = 'configmaps' if resource_type == 'configmap' else 'secrets'
        defaults = DEMO_CONFIGMAPS if resource_type == 'configmap' else DEMO_SECRETS
        items = _get_demo_state(cluster.id, cache_name, defaults)
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        for item in items:
            if item.get('name') == name and item.get('namespace') == namespace:
                previous = item.get('data_payload')
                if previous is None:
                    previous = {f'key{i + 1}': f'value{i + 1}' for i in range(item.get('data_count', 1))}
                backup = {
                    'resource_type': resource_type,
                    'name': name,
                    'namespace': namespace,
                    'secret_type': item.get('type', 'Opaque'),
                    'data': previous,
                    'text': _dump_config_text(previous),
                    'updated_at': item.get('updated_at', ''),
                    'updated_by': item.get('updated_by', ''),
                }
                item['data_payload'] = data
                item['data_count'] = len(data)
                item['updated_at'] = now
                item['updated_by'] = username
                _set_demo_state(cluster.id, cache_name, items)
                cache.set(_demo_config_backup_key(cluster.id, resource_type, namespace, name), backup, K8S_DEMO_STATE_CACHE_TTL)
                return {
                    'resource_type': resource_type,
                    'name': name,
                    'namespace': namespace,
                    'secret_type': item.get('type', 'Opaque'),
                    'data': data,
                    'text': _dump_config_text(data),
                    'updated_at': now,
                    'updated_by': username,
                }
        raise ValueError(f'Resource not found: {resource_type}/{namespace}/{name}')

    def _get_live_config_resource(self, cluster, resource_type, namespace, name):
        k8s = _client_mod._get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        if resource_type == 'configmap':
            obj = v1.read_namespaced_config_map(name, namespace)
            data = obj.data or {}
            secret_type = ''
        else:
            obj = v1.read_namespaced_secret(name, namespace)
            data = {}
            for key, value in (obj.data or {}).items():
                try:
                    data[key] = base64.b64decode(value).decode('utf-8')
                except Exception:
                    data[key] = ''
            secret_type = obj.type or 'Opaque'
        return {
            'resource_type': resource_type,
            'name': obj.metadata.name,
            'namespace': obj.metadata.namespace,
            'secret_type': secret_type,
            'resource_version': obj.metadata.resource_version or '',
            'data': {str(key): '' if value is None else str(value) for key, value in data.items()},
            'text': _dump_config_text(data),
            'updated_at': obj.metadata.creation_timestamp.isoformat() if obj.metadata.creation_timestamp else '',
            'updated_by': '',
        }

    def _apply_live_config_resource(self, cluster, resource_type, namespace, name, data, username):
        k8s = _client_mod._get_k8s_client(cluster)
        v1 = k8s.CoreV1Api()
        current = self._get_live_config_resource(cluster, resource_type, namespace, name)
        cache.set(_config_backup_key(cluster.id, resource_type, namespace, name), current, K8S_DEMO_STATE_CACHE_TTL)
        if resource_type == 'configmap':
            body = v1.read_namespaced_config_map(name, namespace)
            body.data = data
            v1.replace_namespaced_config_map(name, namespace, body)
        else:
            body = v1.read_namespaced_secret(name, namespace)
            body.data = {
                key: base64.b64encode(value.encode('utf-8')).decode('utf-8')
                for key, value in data.items()
            }
            v1.replace_namespaced_secret(name, namespace, body)
        refreshed = self._get_live_config_resource(cluster, resource_type, namespace, name)
        refreshed['updated_by'] = username
        return refreshed

    def _get_config_resource(self, cluster, resource_type, namespace, name):
        if _client_mod._is_demo(cluster):
            detail = self._get_demo_config_resource(cluster, resource_type, namespace, name)
            backup = cache.get(_demo_config_backup_key(cluster.id, resource_type, namespace, name))
        else:
            detail = self._get_live_config_resource(cluster, resource_type, namespace, name)
            backup = cache.get(_config_backup_key(cluster.id, resource_type, namespace, name))
        latest_revision = _config_revision_queryset(cluster, resource_type, namespace, name).first()
        detail['rollback_available'] = bool(latest_revision or backup)
        detail['revision_count'] = _config_revision_queryset(cluster, resource_type, namespace, name).count()
        detail['latest_revision_id'] = latest_revision.id if latest_revision else None
        detail['latest_revision_at'] = latest_revision.created_at.isoformat() if latest_revision and latest_revision.created_at else ''
        return detail

    def _get_latest_config_snapshot(self, cluster, resource_type, namespace, name):
        revision = _config_revision_queryset(cluster, resource_type, namespace, name).first()
        if revision:
            snapshot = _serialize_revision(revision)
            snapshot['data'] = _normalize_config_text(revision.content)
            snapshot['text'] = revision.content
            return snapshot

        backup_key = _demo_config_backup_key(cluster.id, resource_type, namespace, name) if _client_mod._is_demo(cluster) else _config_backup_key(cluster.id, resource_type, namespace, name)
        backup = cache.get(backup_key)
        if not backup:
            return None
        return backup

    @action(detail=True, methods=['get'], url_path='config_resource_detail')
    def config_resource_detail(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        try:
            return Response(self._get_config_resource(cluster, resource_type, namespace, name))
        except Exception as e:
            return Response({'detail': f'Failed to load config resource: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='config_resource_preview')
    def config_resource_preview(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.data.get('type', '')
        name = request.data.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        content = request.data.get('content', '')
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            target_data = _normalize_config_text(content)
            target_text = _dump_config_text(target_data)
            return Response({
                'content': target_text,
                'changed': current.get('text', '') != target_text,
                'diff': _build_text_diff(current.get('text', ''), target_text, 'current', 'proposed'),
            })
        except Exception as e:
            return Response({'detail': f'Preview failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='config_resource_update')
    def config_resource_update(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.data.get('type', '')
        name = request.data.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        content = request.data.get('content', '')
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            data = _normalize_config_text(content)
            username = request.user.username if request.user and request.user.is_authenticated else ''
            _create_config_revision(cluster, resource_type, namespace, name, current, username, 'update')
            if _client_mod._is_demo(cluster):
                detail = self._update_demo_config_resource(cluster, resource_type, namespace, name, data, username)
            else:
                detail = self._apply_live_config_resource(cluster, resource_type, namespace, name, data, username)
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            detail['rollback_available'] = True
            detail['revision_count'] = _config_revision_queryset(cluster, resource_type, namespace, name).count()
            return Response({'success': True, 'message': f'{resource_type} updated', 'resource': detail})
        except Exception as e:
            return Response({'detail': f'Update failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'], url_path='config_resource_revisions')
    def config_resource_revisions(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)

        revisions = [
            _serialize_revision(item)
            for item in _config_revision_queryset(cluster, resource_type, namespace, name)[:20]
        ]
        return Response({'count': len(revisions), 'items': revisions})

    @action(detail=True, methods=['get'], url_path='config_resource_revision_preview')
    def config_resource_revision_preview(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        revision_id = request.query_params.get('revision_id')
        if resource_type not in ('configmap', 'secret') or not name or not revision_id:
            return Response({'detail': 'Valid type, name and revision_id are required'}, status=400)

        revision = _config_revision_queryset(cluster, resource_type, namespace, name).filter(id=revision_id).first()
        if not revision:
            return Response({'detail': 'Revision not found'}, status=404)

        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            return Response({
                'revision': _serialize_revision(revision),
                'diff': _build_text_diff(current.get('text', ''), revision.content, 'current', f'revision-{revision.id}'),
            })
        except Exception as e:
            return Response({'detail': f'Failed to load revision preview: {str(e)}'}, status=400)

    @action(detail=True, methods=['get'], url_path='config_resource_rollback_preview')
    def config_resource_rollback_preview(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.query_params.get('type', '')
        name = request.query_params.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        backup = self._get_latest_config_snapshot(cluster, resource_type, namespace, name)
        if not backup:
            return Response({'detail': 'No rollback snapshot available'}, status=404)
        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            return Response({
                'rollback_available': True,
                'backup': backup,
                'diff': _build_text_diff(current.get('text', ''), backup.get('text', ''), 'current', 'rollback'),
            })
        except Exception as e:
            return Response({'detail': f'Failed to load rollback preview: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='config_resource_rollback')
    def config_resource_rollback(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.data.get('type', '')
        name = request.data.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        if resource_type not in ('configmap', 'secret') or not name:
            return Response({'detail': 'Valid type and name are required'}, status=400)
        backup = self._get_latest_config_snapshot(cluster, resource_type, namespace, name)
        if not backup:
            return Response({'detail': 'No rollback snapshot available'}, status=404)
        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            username = request.user.username if request.user and request.user.is_authenticated else ''
            _create_config_revision(cluster, resource_type, namespace, name, current, username, 'rollback')
            if _client_mod._is_demo(cluster):
                detail = self._update_demo_config_resource(cluster, resource_type, namespace, name, backup.get('data', {}), username)
            else:
                detail = self._apply_live_config_resource(cluster, resource_type, namespace, name, backup.get('data', {}), username)
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            detail['rollback_available'] = True
            detail['revision_count'] = _config_revision_queryset(cluster, resource_type, namespace, name).count()
            return Response({'success': True, 'message': f'{resource_type} rolled back', 'resource': detail})
        except Exception as e:
            return Response({'detail': f'Rollback failed: {str(e)}'}, status=400)

    @action(detail=True, methods=['post'], url_path='config_resource_rollback_to_revision')
    def config_resource_rollback_to_revision(self, request, pk=None):
        cluster = self.get_object()
        resource_type = request.data.get('type', '')
        name = request.data.get('name', '')
        namespace, scope_error = resolve_scope(request, cluster)
        if scope_error:
            return scope_error
        revision_id = request.data.get('revision_id')
        if resource_type not in ('configmap', 'secret') or not name or not revision_id:
            return Response({'detail': 'Valid type, name and revision_id are required'}, status=400)

        revision = _config_revision_queryset(cluster, resource_type, namespace, name).filter(id=revision_id).first()
        if not revision:
            return Response({'detail': 'Revision not found'}, status=404)

        try:
            current = self._get_config_resource(cluster, resource_type, namespace, name)
            target_data = _normalize_config_text(revision.content)
            username = request.user.username if request.user and request.user.is_authenticated else ''
            _create_config_revision(cluster, resource_type, namespace, name, current, username, 'rollback')
            if _client_mod._is_demo(cluster):
                detail = self._update_demo_config_resource(cluster, resource_type, namespace, name, target_data, username)
            else:
                detail = self._apply_live_config_resource(cluster, resource_type, namespace, name, target_data, username)
            _cache_mod._invalidate_cluster_runtime_cache(cluster)
            detail['rollback_available'] = True
            detail['revision_count'] = _config_revision_queryset(cluster, resource_type, namespace, name).count()
            return Response({
                'success': True,
                'message': f'{resource_type} rolled back to revision #{revision.id}',
                'resource': detail,
                'revision': _serialize_revision(revision),
            })
        except Exception as e:
            return Response({'detail': f'Rollback failed: {str(e)}'}, status=400)
