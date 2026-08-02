
from django.contrib import admin
from .models import Curso, PPC, ComponenteCurricular, RelacaoComponente, Bibliografia, Apendice, DinamicaEAD

admin.site.register(Curso)
admin.site.register(PPC)
admin.site.register(ComponenteCurricular)
admin.site.register(RelacaoComponente)
admin.site.register(Bibliografia)
admin.site.register(Apendice)
admin.site.register(DinamicaEAD)

