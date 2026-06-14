# ⚽ Polla del Mundial 2026

Aplicación web para hacer predicciones del Mundial de Fútbol 2026 con familia y amigos. Cada participante predice los marcadores de los partidos, gana puntos por acertar el ganador (3 pts) o el marcador exacto (5 pts), y compite en tablas de posiciones privadas por grupo.

## Características

- **Predicciones en tiempo real** — ingresa tu marcador directamente en la lista de partidos sin navegar a otra página
- **Grupos privados** — crea tu propio grupo con código de invitación; cada grupo tiene su propia tabla de posiciones
- **Llaves del torneo** — vista visual del bracket completo con líneas conectoras y auto-escala
- **Actualización automática de resultados** — sincroniza marcadores desde football-data.org con un script
- **Tabla de posiciones** — con medallas 🥇🥈🥉, puntos exactos y ganadores
- **Panel de administrador** — para registrar resultados manualmente

## Tech Stack

| Capa | Tecnología |
|------|------------|
| Backend | Python 3.11 · FastAPI · SQLModel |
| Base de datos | SQLite (desarrollo) / PostgreSQL (producción) |
| Frontend | Jinja2 templates · Vanilla JS · CSS Variables |
| Auth | Cookies firmadas con itsdangerous |
| Deploy | Docker · AWS App Runner / Amplify |

---

## Correr localmente

### Requisitos
- Python 3.11+
- `pip`

### Pasos

```bash
# 1. Clonar el repo
git clone git@github.com:DavidZapataN/Pagina_Mundial.git
cd Pagina_Mundial

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Copiar variables de entorno
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
# Edita .env y pon tu SECRET_KEY

# 5. Arrancar el servidor
python -m uvicorn app.main:app --app-dir src --reload

# La app corre en http://127.0.0.1:8000
```

### Cargar partidos del Mundial 2026

```bash
python scripts/seed_2026_matches.py
```

### Actualizar resultados automáticamente

```bash
# Registrarte gratis en https://www.football-data.org/client/register
# Luego:
set FOOTBALL_API_KEY=tu_clave_aqui   # Windows
# export FOOTBALL_API_KEY=tu_clave    # macOS/Linux

python scripts/update_results.py

# Para mantenerlo corriendo cada 5 minutos (Windows PowerShell):
while ($true) { python scripts\update_results.py; Start-Sleep 300 }
```

---

## Variables de entorno

| Variable | Descripción | Por defecto |
|----------|-------------|-------------|
| `DATABASE_URL` | URL de conexión a la BD | `sqlite:///world_cup.db` |
| `SECRET_KEY` | Clave para firmar sesiones | `dev-secret-change-in-production` |
| `DEBUG` | Modo debug (muestra SQL) | `false` |
| `ADMIN_USERNAME` | Usuario con privilegios admin | `admin` |
| `FOOTBALL_API_KEY` | Clave de football-data.org | *(vacío)* |

---

## Desplegar en AWS

### Opción A — AWS App Runner (recomendado)

App Runner detecta el `Dockerfile` y despliega el contenedor automáticamente.

1. En la [consola de AWS App Runner](https://console.aws.amazon.com/apprunner), clic en **Create service**
2. Fuente: **Source code repository** → conectar con GitHub → seleccionar `DavidZapataN/Pagina_Mundial`
3. Runtime: **Docker** (detecta el `Dockerfile` automáticamente)
4. Puerto: **8000**
5. En **Environment variables**, configurar:
   ```
   DATABASE_URL = sqlite:////app/data/world_cup.db
   SECRET_KEY   = una-clave-larga-y-aleatoria
   ADMIN_USERNAME = tu_usuario_admin
   ```
6. Clic en **Create & deploy**

> **Nota sobre la base de datos:** SQLite almacena los datos dentro del contenedor. Para no perder datos entre despliegues, monta un volumen EFS en `/app/data` o migra a PostgreSQL (RDS) cambiando `DATABASE_URL`.

### Opción B — AWS Amplify Hosting

1. En la [consola de Amplify](https://console.aws.amazon.com/amplify), clic en **Create new app**
2. Fuente: **GitHub** → seleccionar `DavidZapataN/Pagina_Mundial`
3. Framework: **Web Compute** (para apps con servidor)
4. Amplify usa el `amplify.yml` y el `Dockerfile` para construir y desplegar
5. Configurar variables de entorno en **App settings → Environment variables**
6. Puerto de la app: **8000** (configurar en **App settings → Rewrites and redirects**)

### Opción C — Docker manual (VPS / EC2)

```bash
# Construir la imagen
docker build -t polla-mundial .

# Correr con volumen persistente para la BD
docker run -d \
  -p 8000:8000 \
  -v /home/ubuntu/polla-data:/app/data \
  -e SECRET_KEY="tu-clave-secreta" \
  -e ADMIN_USERNAME="admin" \
  --name polla \
  polla-mundial

# Cargar los partidos (solo la primera vez)
docker exec polla python scripts/seed_2026_matches.py
```

---

## Estructura del proyecto

```
Pagina_Mundial/
├── src/app/
│   ├── main.py              # Entrada de la app FastAPI
│   ├── models.py            # Modelos SQLModel (BD)
│   ├── config.py            # Variables de entorno
│   ├── modules/
│   │   ├── auth/            # Login / registro / sesiones
│   │   ├── matches/         # Partidos y resultados
│   │   ├── predictions/     # Predicciones y puntos
│   │   ├── leaderboard/     # Tabla de posiciones general
│   │   └── groups/          # Grupos privados
│   └── templates/           # Vistas Jinja2
├── scripts/
│   ├── seed_2026_matches.py # Carga partidos del Mundial 2026
│   └── update_results.py    # Sincroniza resultados desde la API
├── Dockerfile
├── amplify.yml
├── requirements.txt
└── .env.example
```

---

## Licencia

Proyecto personal para uso familiar y de amigos. Sin fines comerciales.
