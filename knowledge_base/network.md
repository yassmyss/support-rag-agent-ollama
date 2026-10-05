# Conectividad y DNS

## Sin acceso a un servicio por nombre
1. Confirmar si existe conectividad IP con otros destinos.
2. Ejecutar `nslookup dominio` para comprobar resolución DNS.
3. Comparar el resultado con otro equipo de la misma red cuando sea posible.
4. Revisar la configuración DNS del adaptador sin modificarla hasta conocer la política corporativa.
5. Limpiar la caché DNS con `ipconfig /flushdns` cuando proceda.
6. No cambiar servidores DNS corporativos por servidores públicos sin autorización.

## Escalado
Escalar si afecta a múltiples usuarios, existe pérdida general de conectividad o se sospecha una incidencia de infraestructura.

