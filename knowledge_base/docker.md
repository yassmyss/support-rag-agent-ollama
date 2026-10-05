# Docker Desktop / WSL

## Docker Desktop no inicia en Windows
1. Confirmar que la virtualización está habilitada.
2. Ejecutar `wsl --status` y comprobar que WSL está disponible.
3. Ejecutar `wsl --shutdown`, esperar unos segundos y volver a iniciar Docker Desktop.
4. Revisar el estado del servicio Docker Desktop Service desde Servicios de Windows.
5. Si WSL informa de componentes desactualizados, ejecutar `wsl --update` con permisos adecuados.
6. No eliminar distribuciones, imágenes, volúmenes ni datos del usuario como primera medida.
7. Si persiste el error, recopilar el mensaje exacto y los logs antes de escalar.

## Escalado
Escalar a N2 cuando haya corrupción de WSL, errores persistentes del hipervisor o riesgo de pérdida de datos.

## Contenedor detenido
1. Identificar el contenedor mediante `docker ps -a`.
2. Consultar su salida con `docker logs NOMBRE_O_ID`.
3. Consultar estado, código de salida y motivo informado con `docker inspect NOMBRE_O_ID`.
4. Si aparece `OOMKilled`, comprobar límites de memoria y disponibilidad del host. El código 137 por sí solo no confirma falta de memoria.
5. Registrar errores de configuración y contrastarlos con la configuración esperada sin exponer secretos.
6. No borrar ni recrear contenedores o volúmenes como primera medida. No reiniciar producción sin validar el impacto.
7. Aportar código de salida, logs relevantes y cambios recientes al escalar.
