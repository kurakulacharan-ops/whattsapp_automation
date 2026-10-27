@echo off
setlocal
pushd "%~dp0.." || exit /b 1
if not exist "deploy\runtime.env" (
    echo Missing deploy\runtime.env. Copy your application .env there and configure MSSQL and application secrets.
    popd
    exit /b 1
)
docker compose --env-file deploy\build.env.example -f deploy\docker-compose.production.yml -f deploy\docker-compose.build.yml config --quiet
if errorlevel 1 (
    popd
    exit /b 1
)
docker compose --env-file deploy\build.env.example -f deploy\docker-compose.production.yml -f deploy\docker-compose.build.yml up --build -d --wait --wait-timeout 180
set "attendance_exit=%ERRORLEVEL%"
popd
exit /b %attendance_exit%
