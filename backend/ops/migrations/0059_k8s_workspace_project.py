# Kubernetes 企业空间 / 项目

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ops', '0058_taskresourcegroup_event_environment'),
    ]

    operations = [
        migrations.CreateModel(
            name='K8sWorkspace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=63, unique=True, validators=[django.core.validators.RegexValidator(message='只能包含小写字母、数字和中划线，且必须以字母或数字开头结尾（DNS-1123）。', regex='^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')], verbose_name='标识')),
                ('display_name', models.CharField(max_length=128, verbose_name='名称')),
                ('description', models.CharField(blank=True, default='', max_length=256, verbose_name='描述')),
                ('quota', models.JSONField(blank=True, default=dict, verbose_name='配额')),
                ('status', models.CharField(choices=[('active', '启用'), ('disabled', '停用')], default='active', max_length=16, verbose_name='状态')),
                ('created_by', models.CharField(blank=True, default='', max_length=64, verbose_name='创建人')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('cluster', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='workspaces', to='ops.k8scluster', verbose_name='所属集群')),
            ],
            options={
                'verbose_name': 'K8s 企业空间',
                'verbose_name_plural': 'K8s 企业空间',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='K8sProject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('namespace', models.CharField(max_length=253, validators=[django.core.validators.RegexValidator(message='只能包含小写字母、数字和中划线，且必须以字母或数字开头结尾（DNS-1123）。', regex='^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')], verbose_name='命名空间')),
                ('display_name', models.CharField(max_length=128, verbose_name='名称')),
                ('description', models.CharField(blank=True, default='', max_length=256, verbose_name='描述')),
                ('provision_mode', models.CharField(choices=[('create', '平台创建'), ('adopt', '纳管已有')], default='create', max_length=16, verbose_name='创建方式')),
                ('quota', models.JSONField(blank=True, default=dict, verbose_name='配额')),
                ('limit_range', models.JSONField(blank=True, default=dict, verbose_name='默认资源限制')),
                ('quota_enforced', models.BooleanField(default=False, verbose_name='下发配额到集群')),
                ('created_by', models.CharField(blank=True, default='', max_length=64, verbose_name='创建人')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('cluster', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='k8s_projects', to='ops.k8scluster')),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='projects', to='ops.k8sworkspace')),
            ],
            options={
                'verbose_name': 'K8s 项目',
                'verbose_name_plural': 'K8s 项目',
                'ordering': ['-created_at', '-id'],
                'unique_together': {('cluster', 'namespace')},
            },
        ),
        migrations.CreateModel(
            name='K8sWorkspaceMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('admin', '空间管理员'), ('regular', '普通成员'), ('viewer', '只读成员')], default='regular', max_length=16, verbose_name='角色')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='加入时间')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='k8s_workspace_memberships', to=settings.AUTH_USER_MODEL)),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='ops.k8sworkspace')),
            ],
            options={
                'verbose_name': 'K8s 企业空间成员',
                'verbose_name_plural': 'K8s 企业空间成员',
                'ordering': ['workspace_id', 'user_id'],
                'unique_together': {('workspace', 'user')},
            },
        ),
        migrations.CreateModel(
            name='K8sProjectMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('admin', '空间管理员'), ('regular', '普通成员'), ('viewer', '只读成员')], default='regular', max_length=16, verbose_name='角色')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='加入时间')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='ops.k8sproject')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='k8s_project_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'K8s 项目成员',
                'verbose_name_plural': 'K8s 项目成员',
                'ordering': ['project_id', 'user_id'],
                'unique_together': {('project', 'user')},
            },
        ),
    ]
