from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_auto_20250910_1118'),
    ]

    operations = [
        # Campos já existem no modelo, removendo operações conflitantes
        # migrations.AddField(
        #     model_name='videogerado',
        #     name='caminho_audio_narrador',
        #     field=models.CharField(max_length=500, blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='videogerado',
        #     name='caminho_legenda_ass',
        #     field=models.CharField(max_length=500, blank=True, null=True),
        # ),
        # migrations.AddField(
        #     model_name='videogerado',
        #     name='caminho_imagem_texto',
        #     field=models.CharField(max_length=500, blank=True, null=True),
        # ),
    ]
