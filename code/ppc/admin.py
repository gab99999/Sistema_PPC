
from django.contrib import admin
from .models import Curso, PPC, ComponenteCurricular, RelacaoComponente, Bibliografia, Apendice, DinamicaEAD
from simple_history.admin import SimpleHistoryAdmin

admin.site.register(PPC, SimpleHistoryAdmin)
admin.site.register(Curso, SimpleHistoryAdmin)
admin.site.register(ComponenteCurricular, SimpleHistoryAdmin)
admin.site.register(RelacaoComponente, SimpleHistoryAdmin)
admin.site.register(Bibliografia, SimpleHistoryAdmin)
admin.site.register(Apendice, SimpleHistoryAdmin)
admin.site.register(DinamicaEAD, SimpleHistoryAdmin)

