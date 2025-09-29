from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_alter_assinatura_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='videogerado',
            name='notificacao_vista',
            field=models.BooleanField(default=False),
        ),
    ]
