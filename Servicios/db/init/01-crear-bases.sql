-- Una base de datos por servicio, dentro del mismo contenedor de Postgres.
-- Cada servicio conoce unicamente el nombre de la suya (DB_NAME en docker-compose.yml)
-- y ninguno hace JOIN ni consultas directas contra las tablas de otro servicio.
-- Postgres ejecuta este script UNA sola vez, la primera vez que arranca con el volumen vacio.
-- En produccion serian instancias/servidores separados; aqui comparten contenedor para que
-- la demo quepa en una laptop (ver PRD seccion 8).

CREATE DATABASE usuarios;
CREATE DATABASE eventos;
CREATE DATABASE reservas;
CREATE DATABASE pagos;
CREATE DATABASE boletos;
-- Notificaciones usa MongoDB (base documental), no Postgres: ver servicio `mongo` en docker-compose.yml.
