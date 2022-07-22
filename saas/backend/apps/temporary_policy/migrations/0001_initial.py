# Generated by Django 2.2.25 on 2022-03-08 11:34

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='TemporaryPolicy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creator', models.CharField(max_length=64, verbose_name='创建者')),
                ('updater', models.CharField(max_length=64, verbose_name='更新者')),
                ('created_time', models.DateTimeField(auto_now_add=True)),
                ('updated_time', models.DateTimeField(auto_now=True)),
                ('subject_type', models.CharField(max_length=32)),
                ('subject_id', models.CharField(max_length=64)),
                ('system_id', models.CharField(max_length=32)),
                ('action_type', models.CharField(default='', max_length=32, verbose_name='操作类型')),
                ('action_id', models.CharField(max_length=64, verbose_name='操作ID')),
                ('_resources', models.TextField(db_column='resources', verbose_name='资源策略')),
                ('expired_at', models.IntegerField(verbose_name='过期时间')),
                ('policy_id', models.BigIntegerField(default=0, verbose_name='后端policy_id')),
            ],
            options={
                'verbose_name': '临时权限策略',
                'verbose_name_plural': '临时权限策略',
                'index_together': {('subject_id', 'subject_type', 'system_id')},
            },
        ),
    ]