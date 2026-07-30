cd code                              --> entra na pasta code
cd ..                                --> sobe uma pasta (volta pro nível anterior)
cd ..\..                             --> sobe duas pastas de uma vez
dir                                  --> lista o que tem na pasta atual

..\.venv\Scripts\Activate.ps1        --> ativa o venv (rodando de dentro de code)
.venv\Scripts\Activate.ps1           --> ativa o venv (rodando da raiz do repo)
deactivate                           --> desativa o venv

docker compose up -d                 --> sobe os containers em segundo plano
docker compose down                  --> derruba os containers
docker ps                            --> lista containers rodando no momento
docker ps -a                         --> lista todos os containers (rodando ou não)

python manage.py runserver           --> roda o servidor Django local
python manage.py dbshell             --> abre o terminal MySQL conectado ao banco
python manage.py migrate             --> aplica as migrações no banco (⚠️ cuidado no banco de produção)
python manage.py makemigrations      --> gera novas migrações a partir de mudanças nos models